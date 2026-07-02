import subprocess
import time
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


def smoothstep(fraction: float) -> float:
    clamped = max(0.0, min(1.0, fraction))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def interpolate_pose(start: PoseSpec, end: PoseSpec, fraction: float) -> PoseSpec:
    eased = smoothstep(fraction)
    return PoseSpec(
        x=start.x + (end.x - start.x) * eased,
        y=start.y + (end.y - start.y) * eased,
        z=start.z + (end.z - start.z) * eased,
        qx=start.qx + (end.qx - start.qx) * eased,
        qy=start.qy + (end.qy - start.qy) * eased,
        qz=start.qz + (end.qz - start.qz) * eased,
        qw=start.qw + (end.qw - start.qw) * eased,
    )


DOOR_SPECS: Dict[int, DoorSpec] = {
    1: DoorSpec(
        tag_entity="apriltag_door_outward_1",
        panel_entity="door_outward_panel",
        tag_closed=PoseSpec(
            3.14,
            -0.5115,
            0.45,
            0.5000018366025517,
            -0.49999999999662686,
            -0.49999999999662686,
            -0.4999981633974483,
        ),
        tag_open=PoseSpec(
            3.96,
            -0.5115,
            0.45,
            0.5000018366025517,
            -0.49999999999662686,
            -0.49999999999662686,
            -0.4999981633974483,
        ),
        panel_closed=PoseSpec(3.14, -0.53, 0.42),
        panel_open=PoseSpec(3.96, -0.53, 0.42),
    ),
    2: DoorSpec(
        tag_entity="apriltag_door_inward_2",
        panel_entity="door_inward_panel",
        tag_closed=PoseSpec(
            1.71,
            0.5115,
            0.45,
            0.5000018366025517,
            0.49999999999662686,
            -0.49999999999662686,
            0.4999981633974483,
        ),
        tag_open=PoseSpec(
            0.89,
            0.5115,
            0.45,
            0.5000018366025517,
            0.49999999999662686,
            -0.49999999999662686,
            0.4999981633974483,
        ),
        panel_closed=PoseSpec(1.71, 0.53, 0.42),
        panel_open=PoseSpec(0.89, 0.53, 0.42),
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
        self.declare_parameter("door_motion_duration_sec", 3.0)
        self.declare_parameter("door_motion_update_period_sec", 0.15)

        self.tag_id = int(self.get_parameter("tag_id").value)
        self.world_name = str(self.get_parameter("world_name").value)
        self.service_timeout_ms = int(self.get_parameter("service_timeout_ms").value)
        self.motion_duration_sec = max(
            0.1, float(self.get_parameter("door_motion_duration_sec").value)
        )
        self.motion_update_period_sec = max(
            0.05, float(self.get_parameter("door_motion_update_period_sec").value)
        )
        self.last_visible = None
        self.animation_timer = None
        self.animation_start_time = 0.0

        if self.tag_id not in DOOR_SPECS:
            raise ValueError(f"Unsupported door tag_id: {self.tag_id}")

        spec = DOOR_SPECS[self.tag_id]
        self.current_panel_pose = spec.panel_closed
        self.current_tag_pose = spec.tag_closed
        self.animation_start_panel_pose = spec.panel_closed
        self.animation_start_tag_pose = spec.tag_closed
        self.animation_target_panel_pose = spec.panel_closed
        self.animation_target_tag_pose = spec.tag_closed

        topic = str(self.get_parameter("tag_visible_topic").value)
        self.create_subscription(Bool, topic, self.tag_visible_callback, 10)

        self.get_logger().info(
            f"Controlling Gazebo door state for tag_id={self.tag_id} "
            f"in world={self.world_name}; listening on {topic}; "
            f"sliding motion duration={self.motion_duration_sec:.2f}s, "
            f"update_period={self.motion_update_period_sec:.2f}s."
        )

    def tag_visible_callback(self, msg: Bool) -> None:
        visible = bool(msg.data)

        if self.last_visible == visible:
            return

        self.last_visible = visible
        self.apply_state(visible)

    def apply_state(self, visible: bool) -> None:
        spec = DOOR_SPECS[self.tag_id]

        if visible:
            self.cancel_animation()
            self.current_panel_pose = spec.panel_closed
            self.current_tag_pose = spec.tag_closed
            self.get_logger().info("Applying Gazebo door state: closed/tag visible.")
            self.set_pose(spec.panel_entity, spec.panel_closed)
            self.set_pose(spec.tag_entity, spec.tag_closed)
            return

        self.get_logger().info(
            "Applying Gazebo door state: opening/sliding tag out of FOV."
        )
        self.start_open_animation(spec)

    def start_open_animation(self, spec: DoorSpec) -> None:
        self.cancel_animation()
        self.animation_start_time = time.monotonic()
        self.animation_start_panel_pose = self.current_panel_pose
        self.animation_start_tag_pose = self.current_tag_pose
        self.animation_target_panel_pose = spec.panel_open
        self.animation_target_tag_pose = spec.tag_open
        self.animation_timer = self.create_timer(
            self.motion_update_period_sec,
            self.update_open_animation,
        )
        self.update_open_animation()

    def update_open_animation(self) -> None:
        spec = DOOR_SPECS[self.tag_id]
        elapsed = time.monotonic() - self.animation_start_time
        fraction = min(1.0, elapsed / self.motion_duration_sec)

        panel_pose = interpolate_pose(
            self.animation_start_panel_pose,
            self.animation_target_panel_pose,
            fraction,
        )
        tag_pose = interpolate_pose(
            self.animation_start_tag_pose,
            self.animation_target_tag_pose,
            fraction,
        )

        self.set_pose(spec.panel_entity, panel_pose)
        self.set_pose(spec.tag_entity, tag_pose)
        self.current_panel_pose = panel_pose
        self.current_tag_pose = tag_pose

        if fraction >= 1.0:
            self.cancel_animation()
            self.get_logger().info(
                "Gazebo sliding door open: panel and tag reached side pocket pose."
            )

    def cancel_animation(self) -> None:
        timer = self.animation_timer
        self.animation_timer = None

        if timer is None:
            return

        try:
            timer.cancel()
            self.destroy_timer(timer)
        except Exception:
            pass

    def set_pose(self, entity_name: str, pose: PoseSpec) -> bool:
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
            return False

        self.get_logger().debug(f"Set Gazebo pose for {entity_name}.")
        return True


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DoorStateGazeboController()

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.cancel_animation()
        node.destroy_node()
        shutdown_rclpy_if_needed()


if __name__ == "__main__":
    main()
