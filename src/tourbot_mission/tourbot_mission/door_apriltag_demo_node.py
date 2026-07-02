import threading
import time

import rclpy
from action_msgs.msg import GoalStatus
from apriltag_msgs.msg import AprilTagDetection, AprilTagDetectionArray, Point
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import Bool

from tourbot_interfaces.action import AlignToAprilTag
from tourbot_interfaces.action import DoorTraverse
from tourbot_interfaces.action import WaitForTagRemoved


def shutdown_rclpy_if_needed() -> None:
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass


class DoorAprilTagDemoNode(Node):
    """Deterministic door-flow demo driven by AprilTag detection messages.

    The Gazebo world contains the visual tag models. This node provides the
    controllable camera-side event needed for a repeatable demo: a door tag is
    visible while the door is closed, disappears after a short delay to
    represent the opened door, and the regular behavior action servers execute
    alignment, wait-for-removal, and traversal.
    """

    def __init__(self) -> None:
        super().__init__("door_apriltag_demo_node")

        self.declare_parameter("tag_id", 1)
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("camera_info_topic", "/oakd/rgb/preview/camera_info")
        self.declare_parameter("tag_visible_topic", "/door_demo/tag_visible")
        self.declare_parameter("image_width", 640)
        self.declare_parameter("image_height", 480)
        self.declare_parameter("tag_center_x", 320.0)
        self.declare_parameter("tag_center_y", 240.0)
        self.declare_parameter("visible_before_open_sec", 2.0)
        self.declare_parameter("missing_duration_sec", 1.5)
        self.declare_parameter("wait_timeout_sec", 15.0)
        self.declare_parameter("align_timeout_sec", 8.0)
        self.declare_parameter("x_tolerance_px", 7.0)
        self.declare_parameter("door_wait_seconds", 0.5)
        self.declare_parameter("door_forward_distance", 0.60)
        self.declare_parameter("door_forward_speed", 0.18)
        self.declare_parameter("start_delay_sec", 3.0)
        self.declare_parameter("wait_for_initial_detection_sec", 0.0)
        self.declare_parameter("publish_demo_odom", False)
        self.declare_parameter("publish_synthetic_detections", True)
        self.declare_parameter("publish_camera_info", True)
        self.declare_parameter("demo_odom_topic", "/door_demo/odom")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")

        self.tag_id = int(self.get_parameter("tag_id").value)
        self.image_width = int(self.get_parameter("image_width").value)
        self.image_height = int(self.get_parameter("image_height").value)
        self.tag_center_x = float(self.get_parameter("tag_center_x").value)
        self.tag_center_y = float(self.get_parameter("tag_center_y").value)
        self.visible_before_open_sec = float(
            self.get_parameter("visible_before_open_sec").value
        )
        self.missing_duration_sec = float(
            self.get_parameter("missing_duration_sec").value
        )
        self.wait_timeout_sec = float(self.get_parameter("wait_timeout_sec").value)
        self.align_timeout_sec = float(self.get_parameter("align_timeout_sec").value)
        self.x_tolerance_px = float(self.get_parameter("x_tolerance_px").value)
        self.door_wait_seconds = float(self.get_parameter("door_wait_seconds").value)
        self.door_forward_distance = float(
            self.get_parameter("door_forward_distance").value
        )
        self.door_forward_speed = float(self.get_parameter("door_forward_speed").value)
        self.start_delay_sec = float(self.get_parameter("start_delay_sec").value)
        self.wait_for_initial_detection_sec = float(
            self.get_parameter("wait_for_initial_detection_sec").value
        )
        self.publish_demo_odom = bool(self.get_parameter("publish_demo_odom").value)
        self.publish_synthetic_detections = bool(
            self.get_parameter("publish_synthetic_detections").value
        )
        self.publish_camera_info_enabled = bool(
            self.get_parameter("publish_camera_info").value
        )

        detections_topic = self.get_parameter("detections_topic").value
        camera_info_topic = self.get_parameter("camera_info_topic").value
        tag_visible_topic = self.get_parameter("tag_visible_topic").value
        demo_odom_topic = self.get_parameter("demo_odom_topic").value
        cmd_vel_topic = self.get_parameter("cmd_vel_topic").value

        self.tag_visible = True
        self.demo_complete = False
        self.demo_odom_x = 0.0
        self.demo_odom_y = 0.0
        self.latest_cmd_linear_x = 0.0
        self.last_odom_update_time = time.monotonic()
        self.latest_detections = None

        self.detections_pub = self.create_publisher(
            AprilTagDetectionArray,
            detections_topic,
            10,
        )
        self.camera_info_pub = self.create_publisher(
            CameraInfo,
            camera_info_topic,
            10,
        )
        self.tag_visible_pub = self.create_publisher(
            Bool,
            tag_visible_topic,
            10,
        )
        self.demo_odom_pub = self.create_publisher(
            Odometry,
            demo_odom_topic,
            10,
        )
        self.cmd_vel_sub = self.create_subscription(
            TwistStamped,
            cmd_vel_topic,
            self.cmd_vel_callback,
            10,
        )
        self.detections_sub = self.create_subscription(
            AprilTagDetectionArray,
            detections_topic,
            self.detections_callback,
            10,
        )

        self.align_client = ActionClient(
            self,
            AlignToAprilTag,
            "align_to_apriltag",
        )
        self.wait_client = ActionClient(
            self,
            WaitForTagRemoved,
            "wait_for_tag_removed",
        )
        self.door_client = ActionClient(
            self,
            DoorTraverse,
            "door_traverse",
        )

        self.create_timer(0.1, self.publish_camera_state)

        mode = (
            "synthetic detections"
            if self.publish_synthetic_detections
            else "visual image -> apriltag_ros -> detections"
        )
        self.get_logger().info(f"Door AprilTag demo mode: {mode}.")

        if self.publish_demo_odom:
            self.create_timer(0.05, self.publish_integrated_demo_odom)
            self.get_logger().info(
                f"Publishing integrated demo odom on {demo_odom_topic}."
            )

        self.worker = threading.Thread(target=self.run_demo, daemon=True)
        self.worker.start()

    def cmd_vel_callback(self, msg: TwistStamped) -> None:
        self.latest_cmd_linear_x = float(msg.twist.linear.x)

    def detections_callback(self, msg: AprilTagDetectionArray) -> None:
        self.latest_detections = msg

    def target_tag_visible(self) -> bool:
        if self.latest_detections is None:
            return False

        return any(
            int(detection.id) == self.tag_id
            for detection in self.latest_detections.detections
        )

    def publish_integrated_demo_odom(self) -> None:
        now = time.monotonic()
        dt = now - self.last_odom_update_time
        self.last_odom_update_time = now

        self.demo_odom_x += self.latest_cmd_linear_x * dt

        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "odom"
        msg.child_frame_id = "base_link"
        msg.pose.pose.position.x = self.demo_odom_x
        msg.pose.pose.position.y = self.demo_odom_y
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = self.latest_cmd_linear_x

        self.demo_odom_pub.publish(msg)

    def make_camera_info(self) -> CameraInfo:
        msg = CameraInfo()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "oakd_rgb_camera_optical_frame"
        msg.width = self.image_width
        msg.height = self.image_height
        fx = 525.0
        fy = 525.0
        cx = self.image_width / 2.0
        cy = self.image_height / 2.0
        msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        return msg

    def make_detection(self) -> AprilTagDetection:
        half_size_px = 42.0

        detection = AprilTagDetection()
        detection.family = "36h11"
        detection.id = self.tag_id
        detection.hamming = 0
        detection.goodness = 1.0
        detection.decision_margin = 100.0
        detection.centre = Point(x=self.tag_center_x, y=self.tag_center_y, z=0.0)
        detection.corners = [
            Point(
                x=self.tag_center_x - half_size_px,
                y=self.tag_center_y - half_size_px,
                z=0.0,
            ),
            Point(
                x=self.tag_center_x + half_size_px,
                y=self.tag_center_y - half_size_px,
                z=0.0,
            ),
            Point(
                x=self.tag_center_x + half_size_px,
                y=self.tag_center_y + half_size_px,
                z=0.0,
            ),
            Point(
                x=self.tag_center_x - half_size_px,
                y=self.tag_center_y + half_size_px,
                z=0.0,
            ),
        ]
        detection.homography = [
            1.0,
            0.0,
            self.tag_center_x,
            0.0,
            1.0,
            self.tag_center_y,
            0.0,
            0.0,
            1.0,
        ]
        return detection

    def publish_tag_visible_state(self) -> None:
        visible_msg = Bool()
        visible_msg.data = bool(self.tag_visible)
        self.tag_visible_pub.publish(visible_msg)

    def publish_tag_visible_repeated(
        self,
        visible: bool,
        count: int = 8,
        period_sec: float = 0.05,
    ) -> None:
        self.tag_visible = bool(visible)

        for _ in range(max(1, count)):
            self.publish_tag_visible_state()
            time.sleep(period_sec)

    def publish_camera_state(self) -> None:
        self.publish_tag_visible_state()

        if self.publish_camera_info_enabled:
            self.camera_info_pub.publish(self.make_camera_info())

        if self.publish_synthetic_detections:
            msg = AprilTagDetectionArray()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = "oakd_rgb_camera_optical_frame"

            if self.tag_visible:
                msg.detections.append(self.make_detection())

            self.detections_pub.publish(msg)

    def wait_for_server(self, client: ActionClient, name: str) -> bool:
        self.get_logger().info(f"Waiting for {name} action server...")

        if client.wait_for_server(timeout_sec=15.0):
            return True

        self.get_logger().error(f"{name} action server was not available.")
        return False

    def send_goal_and_wait(self, client: ActionClient, goal_msg, name: str) -> bool:
        self.get_logger().info(f"Sending {name} goal.")

        send_goal_future = client.send_goal_async(goal_msg)

        while rclpy.ok() and not send_goal_future.done():
            time.sleep(0.05)

        goal_handle = send_goal_future.result()

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().error(f"{name} goal was rejected.")
            return False

        result_future = goal_handle.get_result_async()

        while rclpy.ok() and not result_future.done():
            time.sleep(0.05)

        response = result_future.result()

        if response is None:
            self.get_logger().error(f"{name} returned no result response.")
            return False

        if response.status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().error(
                f"{name} failed: status={response.status}, "
                f"message={response.result.message}"
            )
            return False

        if not response.result.success:
            self.get_logger().error(
                f"{name} result was unsuccessful: {response.result.message}"
            )
            return False

        self.get_logger().info(f"{name} succeeded: {response.result.message}")
        return True

    def wait_for_initial_detection(self) -> bool:
        if self.wait_for_initial_detection_sec <= 0.0:
            return True

        deadline = time.monotonic() + self.wait_for_initial_detection_sec
        self.get_logger().info(
            f"Waiting up to {self.wait_for_initial_detection_sec:.1f}s "
            f"for initial detection of tag {self.tag_id}."
        )

        while rclpy.ok() and time.monotonic() < deadline:
            if self.target_tag_visible():
                self.get_logger().info(
                    f"Initial AprilTag {self.tag_id} detection is available."
                )
                return True

            time.sleep(0.05)

        self.get_logger().error(
            f"Timed out waiting for initial detection of tag {self.tag_id}."
        )
        return False

    def run_wait_for_tag_removed(self) -> bool:
        goal = WaitForTagRemoved.Goal()
        goal.tag_id = self.tag_id
        goal.timeout_sec = self.wait_timeout_sec
        goal.missing_duration_sec = self.missing_duration_sec

        self.get_logger().info(
            "Door is CLOSED: publishing visible AprilTag "
            f"{self.tag_id} for {self.visible_before_open_sec:.1f}s."
        )
        self.publish_tag_visible_repeated(True)

        send_goal_future = self.wait_client.send_goal_async(goal)

        while rclpy.ok() and not send_goal_future.done():
            time.sleep(0.05)

        goal_handle = send_goal_future.result()

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().error("wait_for_tag_removed goal was rejected.")
            return False

        result_future = goal_handle.get_result_async()
        open_at = time.monotonic() + self.visible_before_open_sec
        opened = False

        while rclpy.ok() and not result_future.done():
            if not opened and time.monotonic() >= open_at:
                self.publish_tag_visible_repeated(False)
                opened = True
                self.get_logger().info(
                    "Door is OPEN: AprilTag is no longer visible."
                )

            time.sleep(0.05)

        response = result_future.result()

        if response is None:
            self.get_logger().error("wait_for_tag_removed returned no result.")
            return False

        if response.status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().error(
                "wait_for_tag_removed failed: "
                f"status={response.status}, message={response.result.message}"
            )
            return False

        self.get_logger().info(
            f"wait_for_tag_removed succeeded: {response.result.message}"
        )
        return bool(response.result.success)

    def run_demo(self) -> None:
        time.sleep(self.start_delay_sec)

        if not self.wait_for_server(self.align_client, "align_to_apriltag"):
            return
        if not self.wait_for_server(self.wait_client, "wait_for_tag_removed"):
            return
        if not self.wait_for_server(self.door_client, "door_traverse"):
            return

        self.tag_visible = True
        self.publish_tag_visible_repeated(True)

        if not self.wait_for_initial_detection():
            return

        align_goal = AlignToAprilTag.Goal()
        align_goal.tag_id = self.tag_id
        align_goal.timeout_sec = self.align_timeout_sec
        align_goal.x_tolerance_px = self.x_tolerance_px

        if not self.send_goal_and_wait(
            self.align_client,
            align_goal,
            "align_to_apriltag",
        ):
            return

        if not self.run_wait_for_tag_removed():
            return

        door_goal = DoorTraverse.Goal()
        door_goal.tag_id = self.tag_id
        door_goal.backup_distance = 0.0
        door_goal.backup_speed = 0.0
        door_goal.wait_seconds = self.door_wait_seconds
        door_goal.forward_distance = self.door_forward_distance
        door_goal.forward_speed = self.door_forward_speed

        if not self.send_goal_and_wait(
            self.door_client,
            door_goal,
            "door_traverse",
        ):
            return

        self.demo_complete = True
        self.get_logger().info(
            "Door AprilTag demo complete: closed tag detected, tag removed, "
            "and door traversal finished."
        )


def main(args=None) -> None:
    rclpy.init(args=args)

    node = DoorAprilTagDemoNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        shutdown_rclpy_if_needed()
