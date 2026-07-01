from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    EnvironmentVariable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    tag_id = LaunchConfiguration("tag_id")
    ros_domain_id = LaunchConfiguration("ros_domain_id")
    gz_partition = LaunchConfiguration("gz_partition")
    world_name = LaunchConfiguration("world_name")
    custom_gz_args = LaunchConfiguration("custom_gz_args")
    custom_robot_x = LaunchConfiguration("custom_robot_x")
    custom_robot_y = LaunchConfiguration("custom_robot_y")
    custom_robot_z = LaunchConfiguration("custom_robot_z")
    custom_robot_yaw = LaunchConfiguration("custom_robot_yaw")
    start_image_view = LaunchConfiguration("start_image_view")

    tourbot_bringup = FindPackageShare("tourbot_bringup")

    sim_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([tourbot_bringup, "launch", "sim.launch.py"])
    )
    gazebo_demo_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [tourbot_bringup, "launch", "door_apriltag_gazebo_demo.launch.py"]
        )
    )

    start_sim = IncludeLaunchDescription(
        sim_launch,
        launch_arguments={
            "use_custom_sim": "true",
            "start_navigation": "false",
            "custom_world_name": world_name,
            "custom_gz_args": custom_gz_args,
            "custom_robot_x": custom_robot_x,
            "custom_robot_y": custom_robot_y,
            "custom_robot_z": custom_robot_z,
            "custom_robot_yaw": custom_robot_yaw,
        }.items(),
    )

    start_demo = IncludeLaunchDescription(
        gazebo_demo_launch,
        launch_arguments={
            "tag_id": tag_id,
            "use_sim_time": "true",
            "world_name": world_name,
            "start_delay_sec": "4.0",
            "start_image_view": start_image_view,
            "set_initial_robot_pose": "false",
        }.items(),
    )

    set_initial_robot_pose = Node(
        package="tourbot_bringup",
        executable="gazebo_entity_pose_setter",
        name="gazebo_initial_robot_pose",
        output="screen",
        parameters=[
            {
                "world_name": world_name,
                "entity_name": "turtlebot4",
                "x": custom_robot_x,
                "y": custom_robot_y,
                "z": custom_robot_z,
                "yaw": custom_robot_yaw,
                "service_timeout_ms": 3000,
                "repeat_count": 5,
                "repeat_period_sec": 0.5,
            }
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "tag_id",
                default_value="1",
                description="Door AprilTag id to use; default pose targets tag 1.",
            ),
            DeclareLaunchArgument(
                "ros_domain_id",
                default_value=EnvironmentVariable("ROS_DOMAIN_ID", default_value="77"),
                description="ROS_DOMAIN_ID for all launched demo processes.",
            ),
            DeclareLaunchArgument(
                "gz_partition",
                default_value="tourbot_apriltag_gazebo_demo",
                description="Gazebo transport partition for this demo.",
            ),
            DeclareLaunchArgument(
                "world_name",
                default_value="world_demo",
                description="SDF world name used in Gazebo transport topics.",
            ),
            DeclareLaunchArgument(
                "custom_gz_args",
                default_value="-r -s --headless-rendering -v 2",
                description="Gazebo args for the custom world.",
            ),
            DeclareLaunchArgument(
                "custom_robot_x",
                default_value="3.14",
                description="Initial robot x pose; default is tag 1 observation pose.",
            ),
            DeclareLaunchArgument(
                "custom_robot_y",
                default_value="0.0",
                description="Initial robot y pose; default is tag 1 observation pose.",
            ),
            DeclareLaunchArgument(
                "custom_robot_z",
                default_value="0.0",
                description="Initial robot z pose.",
            ),
            DeclareLaunchArgument(
                "custom_robot_yaw",
                default_value="-1.5708",
                description="Initial robot yaw; default faces the tag 1 door.",
            ),
            DeclareLaunchArgument(
                "start_image_view",
                default_value="false",
                description="Open image_view for the Gazebo OAK-D RGB stream.",
            ),
            SetEnvironmentVariable("ROS_DOMAIN_ID", ros_domain_id),
            SetEnvironmentVariable("GZ_PARTITION", gz_partition),
            SetEnvironmentVariable("IGN_PARTITION", gz_partition),
            start_sim,
            TimerAction(period=10.0, actions=[set_initial_robot_pose]),
            TimerAction(period=17.0, actions=[start_demo]),
        ]
    )
