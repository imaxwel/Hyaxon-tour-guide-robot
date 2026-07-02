import subprocess
from dataclasses import dataclass
from typing import Dict

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool


@dataclass(frozen=True)
class PoseSpec:
    x: float
    y: float
    z: float
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0


@dataclass(frozen=True)
class DoorSpec:
    tag_entity: str
    panel_entity: str
    tag_closed: PoseSpec
    tag_open: PoseSpec
    panel_closed: PoseSpec
    panel_open: PoseSpec


DOOR_SPECS: Dict[int, DoorSpec] = {
    1: DoorSpec(
        tag_entity="apriltag_door_outward_1",
        panel_entity="door_outward_panel",
        tag_closed=PoseSpec(
            3.14,
            -0.45,
            0.45,
            0.5000018366025517,
            -0.49999999999662686,
            -0.49999999999662686,
            -0.4999981633974483,
        ),
        tag_open=PoseSpec(
            3.14,
            -3.0,
            0.45,
            0.5000018366025517,
            -0.49999999999662686,
            -0.49999999999662686,
            -0.4999981633974483,
        ),
        panel_closed=PoseSpec(3.14, -0.53, 0.42),
        panel_open=PoseSpec(2.78, -0.89, 0.42, qz=-0.70710678, qw=0.70710678),
    ),
    2: DoorSpec(
        tag_entity="apriltag_door_inward_2",
        panel_entity="door_inward_panel",
        tag_closed=PoseSpec(
            1.71,
            0.45,
            0.45,
            0.5000018366025517,
            0.49999999999662686,
            -0.49999999999662686,
            0.4999981633974483,
        ),
        tag_open=PoseSpec(
            1.71,
            3.0,
            0.45,
            0.5000018366025517,
            0.49999999999662686,
            -0.49999999999662686,
            0.4999981633974483,
        ),
        panel_closed=PoseSpec(1.71, 0.53, 0.42),
        panel_open=PoseSpec(1.35, 0.89, 0.42, qz=0.70710678, qw=0.70710678),
    ),
}


def shutdown_rclpy_if_needed() -> None:
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass


class DoorStateGazeboController(Node):
    """Synchronize demo door state with Gazebo entities."""

    def __init__(self) -> None:
        super().__init__("door_state_gazebo_controller")

        self.declare_parameter("tag_id", 1)
        self.declare_parameter("world_name", "world_demo")
        self.declare_parameter("tag_visible_topic", "/door_demo/tag_visible")
        self.declare_parameter("service_timeout_ms", 2000)

        self.tag_id = int(self.get_parameter("tag_id").value)
        self.world_name = str(self.get_parameter("world_name").value)
        self.service_timeout_ms = int(self.get_parameter("service_timeout_ms").value)
        self.last_visible = None

        if self.tag_id not in DOOR_SPECS:
            raise ValueError(f"Unsupported door tag_id: {self.tag_id}")

        topic = str(self.get_parameter("tag_visible_topic").value)
        self.create_subscription(Bool, topic, self.tag_visible_callback, 10)

        self.get_logger().info(
            f"Controlling Gazebo door state for tag_id={self.tag_id} "
            f"in world={self.world_name}; listening on {topic}."
        )

    def tag_visible_callback(self, msg: Bool) -> None:
        visible = bool(msg.data)

        if self.last_visible == visible:
            return

        self.last_visible = visible
        self.apply_state(visible)

    def apply_state(self, visible: bool) -> None:
        spec = DOOR_SPECS[self.tag_id]
        tag_pose = spec.tag_closed if visible else spec.tag_open
        panel_pose = spec.panel_closed if visible else spec.panel_open

        state = "closed/tag visible" if visible else "open/tag hidden"
        self.get_logger().info(f"Applying Gazebo door state: {state}.")

        self.set_pose(spec.panel_entity, panel_pose)
        self.set_pose(spec.tag_entity, tag_pose)

    def set_pose(self, entity_name: str, pose: PoseSpec) -> None:
        service = f"/world/{self.world_name}/set_pose"
        request = (
            f'name: "{entity_name}" '
            f"position {{ x: {pose.x:.6f} y: {pose.y:.6f} z: {pose.z:.6f} }} "
            "orientation { "
            f"x: {pose.qx:.12f} y: {pose.qy:.12f} "
            f"z: {pose.qz:.12f} w: {pose.qw:.12f} "
            "}"
        )

        command = [
            "gz",
            "service",
            "-s",
            service,
            "--reqtype",
            "gz.msgs.Pose",
            "--reptype",
            "gz.msgs.Boolean",
            "--timeout",
            str(self.service_timeout_ms),
            "--req",
            request,
        ]

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

        output = (result.stdout + result.stderr).strip()

        if result.returncode != 0 or "data: true" not in output:
            self.get_logger().error(
                f"Failed to set Gazebo pose for {entity_name}: {output}"
            )
            return

        self.get_logger().debug(f"Set Gazebo pose for {entity_name}.")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DoorStateGazeboController()

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        shutdown_rclpy_if_needed()


if __name__ == "__main__":
    main()
