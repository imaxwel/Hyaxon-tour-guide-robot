"""Activate Nav2 lifecycle nodes after AMCL publishes map->base_link."""

from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from tf2_ros import Buffer, TransformException, TransformListener


class Nav2PostLocalizationActivator(Node):
    """Wait for localization, then activate any inactive Nav2 lifecycle nodes."""

    def __init__(self):
        super().__init__('nav2_post_localization_activator')

        self.declare_parameter('target_frame', 'map')
        self.declare_parameter('source_frame', 'base_link')
        self.declare_parameter('stable_seconds', 2.0)
        self.declare_parameter('node_names', [
            'controller_server',
            'smoother_server',
            'planner_server',
            'route_server',
            'behavior_server',
            'velocity_smoother',
            'collision_monitor',
            'bt_navigator',
            'waypoint_follower',
            'docking_server',
        ])

        self._target_frame = self.get_parameter('target_frame').value
        self._source_frame = self.get_parameter('source_frame').value
        self._stable_seconds = float(self.get_parameter('stable_seconds').value)
        self._node_names = list(self.get_parameter('node_names').value)

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._get_clients = {}
        self._change_clients = {}
        self._missing_service_logged = set()
        self._retry_counts = {}
        self._tf_ready_since = None
        self._activation_started = False
        self._pending_future = None
        self._current_index = 0
        self._done = False

        self._timer = self.create_timer(1.0, self._on_timer)
        self.get_logger().info(
            f'Waiting for {self._target_frame}->{self._source_frame} before '
            'activating Nav2 lifecycle nodes'
        )

    def _on_timer(self):
        if self._done or self._pending_future is not None:
            return

        if not self._activation_started:
            if not self._localization_ready():
                return
            self._activation_started = True
            self.get_logger().info(
                'Localization transform is available; activating Nav2 nodes'
            )

        self._activate_next_node()

    def _localization_ready(self):
        try:
            self._tf_buffer.lookup_transform(
                self._target_frame,
                self._source_frame,
                rclpy.time.Time(),
            )
        except TransformException:
            self._tf_ready_since = None
            return False

        now_ns = self.get_clock().now().nanoseconds
        if self._tf_ready_since is None or now_ns < self._tf_ready_since:
            self._tf_ready_since = now_ns
            return False

        elapsed = (now_ns - self._tf_ready_since) / 1_000_000_000.0
        return elapsed >= self._stable_seconds

    def _activate_next_node(self):
        while self._current_index < len(self._node_names):
            node_name = self._node_names[self._current_index]
            get_client = self._get_client(node_name)
            if not get_client.service_is_ready():
                if not get_client.wait_for_service(timeout_sec=0.1):
                    self._log_missing_service_once(node_name)
                    return

            future = get_client.call_async(GetState.Request())
            self._pending_future = future
            future.add_done_callback(
                lambda result, name=node_name: self._on_get_state(name, result)
            )
            return

        self._done = True
        self._timer.cancel()
        self.get_logger().info('Nav2 post-localization activation complete')

    def _on_get_state(self, node_name, future):
        self._pending_future = None
        try:
            state = future.result().current_state
        except Exception as exc:  # noqa: BLE001
            self._record_retry(node_name, f'get state failed: {exc}')
            return

        if state.id == State.PRIMARY_STATE_ACTIVE:
            self.get_logger().info(f'{node_name} already active')
            self._current_index += 1
            return

        if state.id == State.PRIMARY_STATE_UNCONFIGURED:
            self._change_state(node_name, Transition.TRANSITION_CONFIGURE)
            return

        if state.id == State.PRIMARY_STATE_INACTIVE:
            self._change_state(node_name, Transition.TRANSITION_ACTIVATE)
            return

        self.get_logger().warning(
            f'{node_name} is in state {state.label}; skipping activation'
        )
        self._current_index += 1

    def _change_state(self, node_name, transition_id):
        change_client = self._change_client(node_name)
        if not change_client.service_is_ready():
            if not change_client.wait_for_service(timeout_sec=0.1):
                self._log_missing_service_once(node_name)
                return

        request = ChangeState.Request()
        request.transition.id = transition_id
        future = change_client.call_async(request)
        self._pending_future = future
        future.add_done_callback(
            lambda result, name=node_name, transition=transition_id:
            self._on_change_state(name, transition, result)
        )

    def _on_change_state(self, node_name, transition_id, future):
        self._pending_future = None
        try:
            success = future.result().success
        except Exception as exc:  # noqa: BLE001
            self._record_retry(node_name, f'change state failed: {exc}')
            return

        if not success:
            self._record_retry(node_name, 'change state returned false')
            return

        if transition_id == Transition.TRANSITION_CONFIGURE:
            self.get_logger().info(f'{node_name} configured')
            return

        self.get_logger().info(f'{node_name} activated')
        self._current_index += 1

    def _get_client(self, node_name):
        if node_name not in self._get_clients:
            self._get_clients[node_name] = self.create_client(
                GetState,
                f'{self._service_prefix(node_name)}/get_state',
            )
        return self._get_clients[node_name]

    def _change_client(self, node_name):
        if node_name not in self._change_clients:
            self._change_clients[node_name] = self.create_client(
                ChangeState,
                f'{self._service_prefix(node_name)}/change_state',
            )
        return self._change_clients[node_name]

    @staticmethod
    def _service_prefix(node_name):
        return node_name if node_name.startswith('/') else f'/{node_name}'

    def _log_missing_service_once(self, node_name):
        if node_name not in self._missing_service_logged:
            self.get_logger().warning(
                f'Waiting for lifecycle services from {node_name}'
            )
            self._missing_service_logged.add(node_name)

    def _record_retry(self, node_name, message):
        retries = self._retry_counts.get(node_name, 0) + 1
        self._retry_counts[node_name] = retries
        if retries > 10:
            self.get_logger().warning(
                f'{node_name}: {message}; skipping after {retries} attempts'
            )
            self._current_index += 1
            return
        self.get_logger().warning(f'{node_name}: {message}; retry {retries}')


def shutdown_rclpy_if_needed():
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass


def main(args=None):
    rclpy.init(args=args)
    node = Nav2PostLocalizationActivator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        shutdown_rclpy_if_needed()


if __name__ == '__main__':
    main()
