from irobot_create_common_bringup.namespace import GetNamespacedName
from irobot_create_common_bringup.offset import OffsetParser

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    namespace = LaunchConfiguration("namespace")
    model = LaunchConfiguration("model")
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    z = LaunchConfiguration("z")
    yaw = LaunchConfiguration("yaw")

    turtlebot4_gz_bringup = FindPackageShare("turtlebot4_gz_bringup")
    turtlebot4_description = FindPackageShare("turtlebot4_description")
    irobot_create_control = FindPackageShare("irobot_create_control")
    irobot_create_gz_bringup = FindPackageShare("irobot_create_gz_bringup")

    ros_gz_bridge_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [turtlebot4_gz_bringup, "launch", "ros_gz_bridge.launch.py"]
        )
    )
    robot_description_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [turtlebot4_description, "launch", "robot_description.launch.py"]
        )
    )
    create3_gz_nodes_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [irobot_create_gz_bringup, "launch", "create3_gz_nodes.launch.py"]
        )
    )
    control_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [irobot_create_control, "launch", "include", "control.py"]
        )
    )

    robot_name = GetNamespacedName(namespace, "turtlebot4")
    dock_name = GetNamespacedName(namespace, "standard_dock")
    z_robot = OffsetParser(z, -0.0025)

    spawn_group = GroupAction(
        [
            PushRosNamespace(namespace),
            IncludeLaunchDescription(
                robot_description_launch,
                launch_arguments={
                    "model": model,
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            Node(
                package="ros_gz_sim",
                executable="create",
                arguments=[
                    "-name",
                    robot_name,
                    "-x",
                    x,
                    "-y",
                    y,
                    "-z",
                    z_robot,
                    "-Y",
                    yaw,
                    "-topic",
                    "robot_description",
                ],
                output="screen",
            ),
            IncludeLaunchDescription(
                ros_gz_bridge_launch,
                launch_arguments={
                    "model": model,
                    "robot_name": robot_name,
                    "dock_name": dock_name,
                    "namespace": namespace,
                    "world": world,
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            IncludeLaunchDescription(
                create3_gz_nodes_launch,
                launch_arguments={
                    "robot_name": robot_name,
                    "dock_name": dock_name,
                }.items(),
            ),
            IncludeLaunchDescription(
                control_launch,
                launch_arguments={"namespace": namespace}.items(),
            ),
            Node(
                name="rplidar_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "0.0",
                    "rplidar_link",
                    [robot_name, "/rplidar_link/rplidar"],
                ],
                remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
            ),
            Node(
                name="camera_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "1.5707",
                    "-1.5707",
                    "0",
                    "oakd_rgb_camera_optical_frame",
                    [robot_name, "/oakd_rgb_camera_frame/rgbd_camera"],
                ],
                remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
            ),
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("rviz", default_value="false"),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("model", default_value="standard"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("world", default_value="world_demo"),
            DeclareLaunchArgument("x", default_value="0.0"),
            DeclareLaunchArgument("y", default_value="0.0"),
            DeclareLaunchArgument("z", default_value="0.0"),
            DeclareLaunchArgument("yaw", default_value="0.0"),
            spawn_group,
        ]
    )
