"""Republish odometry pose as a standard volatile TF transform."""

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from tf2_ros import TransformBroadcaster


class OdomTfCompat(Node):
    """Bridge /odom's pose into /tf with QoS compatible with Nav2 listeners."""

    def __init__(self):
        super().__init__('odom_tf_compat')

        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('parent_frame', 'odom')
        self.declare_parameter('child_frame', 'base_link')
        self.declare_parameter('use_odom_frame_ids', True)

        odom_topic = self.get_parameter('odom_topic').value
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._tf_broadcaster = TransformBroadcaster(self)
        self._subscription = self.create_subscription(
            Odometry,
            odom_topic,
            self._on_odom,
            qos,
        )
        self.get_logger().info(
            f'Republishing {odom_topic} pose as volatile odom->base_link TF'
        )

    def _on_odom(self, msg):
        use_odom_frame_ids = self.get_parameter('use_odom_frame_ids').value
        parent_frame = self.get_parameter('parent_frame').value
        child_frame = self.get_parameter('child_frame').value

        if use_odom_frame_ids:
            parent_frame = msg.header.frame_id or parent_frame
            child_frame = msg.child_frame_id or child_frame

        transform = TransformStamped()
        transform.header.stamp = msg.header.stamp
        transform.header.frame_id = parent_frame
        transform.child_frame_id = child_frame
        transform.transform.translation.x = msg.pose.pose.position.x
        transform.transform.translation.y = msg.pose.pose.position.y
        transform.transform.translation.z = msg.pose.pose.position.z
        transform.transform.rotation = msg.pose.pose.orientation

        self._tf_broadcaster.sendTransform(transform)


def shutdown_rclpy_if_needed():
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass


def main(args=None):
    rclpy.init(args=args)
    node = OdomTfCompat()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        shutdown_rclpy_if_needed()


if __name__ == '__main__':
    main()
