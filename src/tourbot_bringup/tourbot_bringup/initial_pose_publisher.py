import math

from geometry_msgs.msg import PoseWithCovarianceStamped
import rclpy
from rclpy.node import Node


class InitialPosePublisher(Node):
    def __init__(self):
        super().__init__('tourbot_initial_pose_publisher')
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('x', 0.0)
        self.declare_parameter('y', 0.0)
        self.declare_parameter('yaw', 0.0)
        self.declare_parameter('period', 1.0)
        self.declare_parameter('count', 20)

        self.frame_id = self.get_parameter('frame_id').value
        self.x = float(self.get_parameter('x').value)
        self.y = float(self.get_parameter('y').value)
        self.yaw = float(self.get_parameter('yaw').value)
        self.remaining = int(self.get_parameter('count').value)

        self.pub = self.create_publisher(PoseWithCovarianceStamped, 'initialpose', 10)
        self.timer = self.create_timer(
            float(self.get_parameter('period').value),
            self.publish_pose,
        )

    def publish_pose(self):
        if self.remaining <= 0:
            self.get_logger().info('Initial pose publishing complete')
            rclpy.shutdown()
            return

        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = self.frame_id
        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        msg.pose.pose.orientation.z = math.sin(self.yaw * 0.5)
        msg.pose.pose.orientation.w = math.cos(self.yaw * 0.5)
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.06853891945200942

        self.pub.publish(msg)
        self.remaining -= 1
        self.get_logger().info(
            f'Published initial pose x={self.x:.3f} y={self.y:.3f} yaw={self.yaw:.3f}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = InitialPosePublisher()
    try:
        rclpy.spin(node)
    finally:
        if rclpy.ok():
            node.destroy_node()


if __name__ == '__main__':
    main()
