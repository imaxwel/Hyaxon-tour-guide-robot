from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    tag_id = LaunchConfiguration("tag_id")
    use_sim_time = LaunchConfiguration("use_sim_time")
    start_image_view = LaunchConfiguration("start_image_view")

    tourbot_perception = FindPackageShare("tourbot_perception")
    apriltag_config = PathJoinSubstitution(
        [tourbot_perception, "config", "apriltags_36h11.yaml"]
    )

    visual_camera = Node(
        package="tourbot_perception",
        executable="door_visual_camera_node",
        name="door_visual_camera_node",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "tag_id": tag_id,
            }
        ],
    )

    apriltag_detector = Node(
        package="apriltag_ros",
        executable="apriltag_node",
        name="apriltag",
        output="screen",
        parameters=[
            apriltag_config,
            {"use_sim_time": use_sim_time},
        ],
        remappings=[
            ("image_rect", "/oakd/rgb/preview/image_raw"),
            ("camera_info", "/oakd/rgb/preview/camera_info"),
            ("detections", "/detections"),
        ],
    )

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
                "publish_synthetic_detections": False,
                "publish_camera_info": False,
                "start_delay_sec": 4.0,
            }
        ],
    )

    image_view = Node(
        package="image_view",
        executable="image_view",
        name="door_demo_image_view",
        output="screen",
        condition=IfCondition(start_image_view),
        remappings=[
            ("image", "/door_demo/visualization/image_raw"),
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "tag_id",
                default_value="1",
                description="Door AprilTag id to use; 1=outward, 2=inward.",
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="true",
                description="Use /clock from Gazebo when Terminal A is running.",
            ),
            DeclareLaunchArgument(
                "start_image_view",
                default_value="true",
                description="Open an image_view window with the annotated door camera.",
            ),
            visual_camera,
            apriltag_detector,
            image_view,
            align_to_apriltag_server,
            wait_for_tag_removed_server,
            door_behavior_server,
            TimerAction(period=2.0, actions=[door_apriltag_demo_node]),
        ]
    )
