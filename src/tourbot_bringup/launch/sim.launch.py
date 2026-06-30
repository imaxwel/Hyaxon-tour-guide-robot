from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    turtlebot4_gz_bringup = FindPackageShare('turtlebot4_gz_bringup')
    turtlebot4_navigation = FindPackageShare('turtlebot4_navigation')
    turtlebot4_viz = FindPackageShare('turtlebot4_viz')
    tourbot_bringup = FindPackageShare('tourbot_bringup')

    use_custom_sim = LaunchConfiguration('use_custom_sim')
    custom_world = LaunchConfiguration('custom_world')
    custom_map = LaunchConfiguration('custom_map')

    turtlebot4_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_gz_bringup,
            'launch',
            'turtlebot4_gz.launch.py',
        ])
    )

    localization_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_navigation,
            'launch',
            'localization.launch.py',
        ])
    )

    nav2_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_navigation,
            'launch',
            'nav2.launch.py',
        ])
    )

    rviz_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_viz,
            'launch',
            'view_navigation.launch.py',
        ])
    )

    default_sim = IncludeLaunchDescription(
        turtlebot4_launch,
        condition=UnlessCondition(use_custom_sim),
        launch_arguments={
            'nav2': 'false',
            'slam': 'false',
            'localization': 'false',
            'rviz': 'false',
        }.items(),
    )

    custom_sim = IncludeLaunchDescription(
        turtlebot4_launch,
        condition=IfCondition(use_custom_sim),
        launch_arguments={
            'nav2': 'false',
            'slam': 'false',
            'localization': 'false',
            'rviz': 'false',

            'world': custom_world,
        }.items(),
    )

    default_localization = IncludeLaunchDescription(
        localization_launch,
        condition=UnlessCondition(use_custom_sim),
        launch_arguments={
            'use_sim_time': 'true',
        }.items(),
    )

    custom_localization = IncludeLaunchDescription(
        localization_launch,
        condition=IfCondition(use_custom_sim),
        launch_arguments={
            'use_sim_time': 'true',
            'map': custom_map,
        }.items(),
    )

    delayed_navigation = TimerAction(
        period=30.0,
        actions=[
            default_localization,
            custom_localization,
            IncludeLaunchDescription(
                nav2_launch,
                launch_arguments={
                    'use_sim_time': 'true',
                }.items(),
            ),
            IncludeLaunchDescription(
                rviz_launch,
                launch_arguments={
                    'use_sim_time': 'true',
                }.items(),
            ),
        ],
    )

    odom_tf_compat = Node(
        package='tourbot_bringup',
        executable='odom_tf_compat',
        name='odom_tf_compat',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'odom_topic': '/odom',
            'parent_frame': 'odom',
            'child_frame': 'base_link',
            'use_odom_frame_ids': True,
        }],
    )

    nav2_post_localization_activator = Node(
        package='tourbot_bringup',
        executable='nav2_post_localization_activator',
        name='nav2_post_localization_activator',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'target_frame': 'map',
            'source_frame': 'base_link',
            'stable_seconds': 2.0,
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_custom_sim',
            default_value='false',
            description='Launch with custom tourbot world and map',
        ),

        DeclareLaunchArgument(
            'custom_world',
            default_value=PathJoinSubstitution([
                tourbot_bringup,
                'worlds',
                'cardboard_city',
                'world',
            ]),
            description='Custom Gazebo world name or path without .sdf suffix',
        ),

        DeclareLaunchArgument(
            'custom_map',
            default_value=PathJoinSubstitution([
                tourbot_bringup,
                'maps',
                'cardboard_city',
                'map_area.yaml',
            ]),
            description='Custom Nav2 map YAML path',
        ),

        default_sim,
        custom_sim,
        odom_tf_compat,
        nav2_post_localization_activator,
        # Start Nav2 after Gazebo, ros2_control, and odom TF have time to appear.
        delayed_navigation,
    ])
