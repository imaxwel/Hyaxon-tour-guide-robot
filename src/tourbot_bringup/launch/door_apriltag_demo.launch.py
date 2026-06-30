from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    tag_id = LaunchConfiguration("tag_id")
    use_sim_time = LaunchConfiguration("use_sim_time")

    align_to_apriltag_server = Node(
        package="tourbot_behaviors",
        executable="align_to_apriltag_server",
        name="align_to_apriltag_server",
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    wait_for_tag_removed_server = Node(
        package="tourbot_behaviors",
        executable="wait_for_tag_removed_server",
        name="wait_for_tag_removed_server",
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    door_behavior_server = Node(
        package="tourbot_behaviors",
        executable="door_behavior_server",
        name="door_behavior_server",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "odom_topic": "/door_demo/odom",
            }
        ],
    )

    door_apriltag_demo_node = Node(
        package="tourbot_mission",
        executable="door_apriltag_demo_node",
        name="door_apriltag_demo_node",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "tag_id": tag_id,
                "publish_demo_odom": True,
            }
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "tag_id",
                default_value="1",
                description="Door AprilTag id to use for the demo; 1=outward, 2=inward.",
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="true",
                description="Use /clock from Gazebo.",
            ),
            align_to_apriltag_server,
            wait_for_tag_removed_server,
            door_behavior_server,
            TimerAction(period=2.0, actions=[door_apriltag_demo_node]),
        ]
    )
