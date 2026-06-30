from ament_index_python.packages import get_package_share_directory

from irobot_create_common_bringup.namespace import GetNamespacedName
from irobot_create_common_bringup.offset import (
    OffsetParser,
    RotationalOffsetX,
    RotationalOffsetY,
)

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():
    pkg_tourbot_bringup = get_package_share_directory('tourbot_bringup')
    pkg_turtlebot4_gz_bringup = get_package_share_directory('turtlebot4_gz_bringup')
    pkg_turtlebot4_description = get_package_share_directory('turtlebot4_description')
    pkg_turtlebot4_navigation = get_package_share_directory('turtlebot4_navigation')
    pkg_turtlebot4_viz = get_package_share_directory('turtlebot4_viz')
    pkg_irobot_create_common_bringup = get_package_share_directory(
        'irobot_create_common_bringup'
    )
    pkg_irobot_create_gz_bringup = get_package_share_directory(
        'irobot_create_gz_bringup'
    )

    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    model = LaunchConfiguration('model')
    world = LaunchConfiguration('world')
    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    z = LaunchConfiguration('z')
    yaw = LaunchConfiguration('yaw')

    robot_name = GetNamespacedName(namespace, 'turtlebot4')
    dock_name = GetNamespacedName(namespace, 'standard_dock')

    dock_offset_x = RotationalOffsetX(0.157, yaw)
    dock_offset_y = RotationalOffsetY(0.157, yaw)
    x_dock = OffsetParser(x, dock_offset_x)
    y_dock = OffsetParser(y, dock_offset_y)
    z_robot = OffsetParser(z, -0.0025)
    yaw_dock = OffsetParser(yaw, 3.1416)

    robot_description_launch = PathJoinSubstitution([
        pkg_turtlebot4_description,
        'launch',
        'robot_description.launch.py',
    ])
    dock_description_launch = PathJoinSubstitution([
        pkg_irobot_create_common_bringup,
        'launch',
        'dock_description.launch.py',
    ])
    turtlebot4_ros_gz_bridge_launch = PathJoinSubstitution([
        pkg_turtlebot4_gz_bringup,
        'launch',
        'ros_gz_bridge.launch.py',
    ])
    turtlebot4_node_launch = PathJoinSubstitution([
        pkg_turtlebot4_gz_bringup,
        'launch',
        'turtlebot4_nodes.launch.py',
    ])
    create3_gz_nodes_launch = PathJoinSubstitution([
        pkg_irobot_create_gz_bringup,
        'launch',
        'create3_gz_nodes.launch.py',
    ])
    create3_nodes_no_control_launch = PathJoinSubstitution([
        pkg_tourbot_bringup,
        'launch',
        'create3_nodes_no_control.launch.py',
    ])
    create3_control_launch = PathJoinSubstitution([
        pkg_tourbot_bringup,
        'launch',
        'create3_sim_control.launch.py',
    ])
    rviz_launch = PathJoinSubstitution([
        pkg_turtlebot4_viz,
        'launch',
        'view_navigation.launch.py',
    ])
    localization_launch = PathJoinSubstitution([
        pkg_turtlebot4_navigation,
        'launch',
        'localization.launch.py',
    ])
    slam_launch = PathJoinSubstitution([
        pkg_turtlebot4_navigation,
        'launch',
        'slam.launch.py',
    ])
    nav2_launch = PathJoinSubstitution([
        pkg_turtlebot4_navigation,
        'launch',
        'nav2.launch.py',
    ])

    param_file_cmd = DeclareLaunchArgument(
        'param_file',
        default_value=PathJoinSubstitution([
            pkg_turtlebot4_gz_bringup,
            'config',
            'turtlebot4_node.yaml',
        ]),
        description='TurtleBot 4 node parameter file',
    )

    spawn_robot_node = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-world',
            world,
            '-name',
            robot_name,
            '-x',
            x,
            '-y',
            y,
            '-z',
            z_robot,
            '-Y',
            yaw,
            '-topic',
            'robot_description',
        ],
        output='screen',
    )

    spawn_dock_node = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-world',
            world,
            '-name',
            dock_name,
            '-x',
            x_dock,
            '-y',
            y_dock,
            '-z',
            z,
            '-Y',
            yaw_dock,
            '-topic',
            'standard_dock_description',
        ],
        output='screen',
    )

    delayed_control_start = TimerAction(
        period=LaunchConfiguration('controller_start_delay'),
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([create3_control_launch]),
                launch_arguments={
                    'namespace': namespace,
                    'controller_manager_timeout': LaunchConfiguration(
                        'controller_manager_timeout'
                    ),
                    'controller_service_call_timeout': LaunchConfiguration(
                        'controller_service_call_timeout'
                    ),
                    'controller_switch_timeout': LaunchConfiguration(
                        'controller_switch_timeout'
                    ),
                }.items(),
            )
        ],
    )

    delayed_robot_nodes_start = TimerAction(
        period=LaunchConfiguration('robot_nodes_start_delay'),
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_ros_gz_bridge_launch]),
                launch_arguments={
                    'use_sim_time': use_sim_time,
                    'model': model,
                    'robot_name': robot_name,
                    'dock_name': dock_name,
                    'namespace': namespace,
                    'world': world,
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_node_launch]),
                launch_arguments={
                    'model': model,
                    'param_file': LaunchConfiguration('param_file'),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([create3_nodes_no_control_launch]),
                launch_arguments={
                    'gazebo': 'ignition',
                    'namespace': namespace,
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([create3_gz_nodes_launch]),
                launch_arguments={
                    'robot_name': robot_name,
                    'dock_name': dock_name,
                }.items(),
            ),
            Node(
                name='rplidar_stf',
                package='tf2_ros',
                executable='static_transform_publisher',
                output='screen',
                arguments=[
                    '0',
                    '0',
                    '0',
                    '0',
                    '0',
                    '0.0',
                    'rplidar_link',
                    [robot_name, '/rplidar_link/rplidar'],
                ],
                remappings=[
                    ('/tf', 'tf'),
                    ('/tf_static', 'tf_static'),
                ],
            ),
            Node(
                name='camera_stf',
                package='tf2_ros',
                executable='static_transform_publisher',
                output='screen',
                arguments=[
                    '0',
                    '0',
                    '0',
                    '1.5707',
                    '-1.5707',
                    '0',
                    'oakd_rgb_camera_optical_frame',
                    [robot_name, '/oakd_rgb_camera_frame/rgbd_camera'],
                ],
                remappings=[
                    ('/tf', 'tf'),
                    ('/tf_static', 'tf_static'),
                ],
            ),
        ],
    )

    spawn_robot_group_action = GroupAction([
        PushRosNamespace(namespace),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([robot_description_launch]),
            launch_arguments={
                'model': model,
                'use_sim_time': use_sim_time,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([dock_description_launch]),
            launch_arguments={'gazebo': 'ignition'}.items(),
        ),
        spawn_robot_node,
        spawn_dock_node,
        delayed_control_start,
        delayed_robot_nodes_start,
    ])

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([localization_launch]),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
        condition=IfCondition(LaunchConfiguration('localization')),
    )

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([slam_launch]),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
        condition=IfCondition(LaunchConfiguration('slam')),
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([nav2_launch]),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
        condition=IfCondition(LaunchConfiguration('nav2')),
    )

    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([rviz_launch]),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'rviz',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'model',
            default_value='lite',
            choices=['standard', 'lite'],
        ),
        DeclareLaunchArgument('namespace', default_value=''),
        DeclareLaunchArgument(
            'localization',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'slam',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'nav2',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument('world', default_value='cardboard_city'),
        DeclareLaunchArgument('x', default_value='0.0'),
        DeclareLaunchArgument('y', default_value='0.0'),
        DeclareLaunchArgument('z', default_value='0.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument(
            'controller_start_delay',
            default_value='10.0',
            description='Delay after robot spawn before loading ros2_control controllers',
        ),
        DeclareLaunchArgument(
            'robot_nodes_start_delay',
            default_value='18.0',
            description='Delay after robot spawn before starting bridges and robot nodes',
        ),
        DeclareLaunchArgument('controller_manager_timeout', default_value='90'),
        DeclareLaunchArgument('controller_service_call_timeout', default_value='45'),
        DeclareLaunchArgument('controller_switch_timeout', default_value='45'),
        param_file_cmd,
        spawn_robot_group_action,
        localization,
        slam,
        nav2,
        rviz,
    ])
