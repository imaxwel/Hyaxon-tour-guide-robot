import math
import subprocess

import rclpy
from rclpy.node import Node


class GazeboEntityPoseSetter(Node):
    """Set a Gazebo entity pose through the gz transport set_pose service."""

    def __init__(self) -> None:
        super().__init__("gazebo_entity_pose_setter")

        self.declare_parameter("world_name", "world_demo")
        self.declare_parameter("entity_name", "turtlebot4")
        self.declare_parameter("x", 0.0)
        self.declare_parameter("y", 0.0)
        self.declare_parameter("z", 0.0)
        self.declare_parameter("yaw", 0.0)
        self.declare_parameter("service_timeout_ms", 3000)
        self.declare_parameter("repeat_count", 1)
        self.declare_parameter("repeat_period_sec", 0.5)

        self.world_name = self._string_param("world_name")
        self.entity_name = self._string_param("entity_name")
        self.x = self._float_param("x")
        self.y = self._float_param("y")
        self.z = self._float_param("z")
        self.yaw = self._float_param("yaw")
        self.service_timeout_ms = self._int_param("service_timeout_ms")
        self.remaining = max(1, self._int_param("repeat_count"))
        self.repeat_period_sec = max(0.05, self._float_param("repeat_period_sec"))

        self.timer = self.create_timer(0.05, self.set_pose_once)

        self.get_logger().info(
            "Setting Gazebo entity pose "
            f"entity={self.entity_name} world={self.world_name} "
            f"pose=({self.x:.3f}, {self.y:.3f}, {self.z:.3f}, yaw={self.yaw:.3f}) "
            f"repeat_count={self.remaining}."
        )

    def _string_param(self, name: str) -> str:
        return str(self.get_parameter(name).value)

    def _float_param(self, name: str) -> float:
        return float(str(self.get_parameter(name).value))

    def _int_param(self, name: str) -> int:
        return int(float(str(self.get_parameter(name).value)))

    def set_pose_once(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
            self.destroy_timer(self.timer)
            self.timer = None

        success = self.set_pose()
        self.remaining -= 1

        if self.remaining <= 0:
            status = "complete" if success else "complete with errors"
            self.get_logger().info(f"Gazebo entity pose setter {status}.")
            rclpy.shutdown()
            return

        self.timer = self.create_timer(self.repeat_period_sec, self.set_pose_once)

    def set_pose(self) -> bool:
        qz = math.sin(self.yaw / 2.0)
        qw = math.cos(self.yaw / 2.0)
        service = f"/world/{self.world_name}/set_pose"
        request = (
            f'name: "{self.entity_name}" '
            f"position {{ x: {self.x:.6f} y: {self.y:.6f} z: {self.z:.6f} }} "
            f"orientation {{ x: 0.0 y: 0.0 z: {qz:.12f} w: {qw:.12f} }}"
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
                f"Failed to set Gazebo pose for {self.entity_name}: {output}"
            )
            return False

        self.get_logger().info(f"Set Gazebo pose for {self.entity_name}.")
        return True


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GazeboEntityPoseSetter()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
