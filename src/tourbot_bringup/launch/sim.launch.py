from launch import LaunchDescription
from launch.actions import (
    AppendEnvironmentVariable,
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    turtlebot4_gz_bringup = FindPackageShare('turtlebot4_gz_bringup')
    turtlebot4_gz_gui_plugins = FindPackageShare('turtlebot4_gz_gui_plugins')
    turtlebot4_navigation = FindPackageShare('turtlebot4_navigation')
    turtlebot4_description = FindPackageShare('turtlebot4_description')
    irobot_create_description = FindPackageShare('irobot_create_description')
    irobot_create_gz_bringup = FindPackageShare('irobot_create_gz_bringup')
    irobot_create_gz_plugins = FindPackageShare('irobot_create_gz_plugins')
    ros_gz_sim = FindPackageShare('ros_gz_sim')
    tourbot_bringup = FindPackageShare('tourbot_bringup')

    use_custom_sim = LaunchConfiguration('use_custom_sim')
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    rviz = LaunchConfiguration('rviz')
    localization = LaunchConfiguration('localization')
    slam = LaunchConfiguration('slam')
    nav2 = LaunchConfiguration('nav2')
    model = LaunchConfiguration('model')
    gazebo_gui = LaunchConfiguration('gazebo_gui')
    custom_world = LaunchConfiguration('custom_world')
    custom_world_name = LaunchConfiguration('custom_world_name')
    custom_map = LaunchConfiguration('custom_map')
    localization_params = LaunchConfiguration('localization_params')
    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    z = LaunchConfiguration('z')
    yaw = LaunchConfiguration('yaw')

    gazebo_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_gz_bringup,
            'launch',
            'sim.launch.py',
        ])
    )
    ros_gz_sim_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            ros_gz_sim,
            'launch',
            'gz_sim.launch.py',
        ])
    )
    spawn_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_gz_bringup,
            'launch',
            'turtlebot4_spawn.launch.py',
        ])
    )
    tour_spawn_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            tourbot_bringup,
            'launch',
            'turtlebot4_tour_spawn.launch.py',
        ])
    )
    localization_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_navigation,
            'launch',
            'localization.launch.py',
        ])
    )
    slam_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_navigation,
            'launch',
            'slam.launch.py',
        ])
    )
    nav2_launch = PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            turtlebot4_navigation,
            'launch',
            'nav2.launch.py',
        ])
    )

    default_gazebo = IncludeLaunchDescription(
        gazebo_launch,
        condition=UnlessCondition(use_custom_sim),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'world': 'warehouse',
            'model': model,
        }.items(),
    )

    custom_gz_resource_path = AppendEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=[
            PathJoinSubstitution([tourbot_bringup, 'worlds']),
            ':',
            PathJoinSubstitution([turtlebot4_gz_bringup, 'worlds']),
            ':',
            PathJoinSubstitution([irobot_create_gz_bringup, 'worlds']),
            ':',
            PathJoinSubstitution([turtlebot4_description, '..']),
            ':',
            PathJoinSubstitution([irobot_create_description, '..']),
        ],
        separator=':',
        prepend=True,
        condition=IfCondition(use_custom_sim),
    )

    custom_gz_gui_plugin_path = AppendEnvironmentVariable(
        name='GZ_GUI_PLUGIN_PATH',
        value=[
            PathJoinSubstitution([turtlebot4_gz_gui_plugins, 'lib']),
            ':',
            PathJoinSubstitution([irobot_create_gz_plugins, 'lib']),
        ],
        separator=':',
        prepend=True,
        condition=IfCondition(use_custom_sim),
    )

    custom_gazebo = IncludeLaunchDescription(
        ros_gz_sim_launch,
        condition=IfCondition(use_custom_sim),
        launch_arguments={
            'gz_args': [
                custom_world,
                '.sdf',
                ' -r',
                ' -s',
                ' -v 4',
                ' --headless-rendering',
                ' --render-engine-server ogre',
            ],
        }.items(),
    )

    custom_gazebo_gui = TimerAction(
        period=3.0,
        actions=[
            IncludeLaunchDescription(
                ros_gz_sim_launch,
                condition=IfCondition(PythonExpression([
                    "'", use_custom_sim, "' == 'true' and '", gazebo_gui, "' == 'true'"
                ])),
                launch_arguments={
                    'gz_args': [
                        ' -g',
                        ' -v 4',
                        ' --render-engine-gui ogre',
                        ' --gui-config ',
                        PathJoinSubstitution([
                            tourbot_bringup,
                            'gui',
                            'cardboard_city',
                            'gui.config',
                        ]),
                    ],
                }.items(),
            )
        ],
    )

    custom_clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        ],
        condition=IfCondition(use_custom_sim),
    )

    def make_spawn(spawn_source, world_name, condition, extra_arguments=None):
        launch_arguments = {
            'namespace': namespace,
            'use_sim_time': use_sim_time,
            'rviz': rviz,
            'model': model,
            'x': x,
            'y': y,
            'z': z,
            'yaw': yaw,
            # Keep this as the SDF world name, not the world file path.
            'world': world_name,
            # Navigation is launched explicitly below so map/custom_map is forwarded.
            'localization': 'false',
            'slam': 'false',
            'nav2': 'false',
        }
        if extra_arguments is not None:
            launch_arguments.update(extra_arguments)

        return GroupAction(
            scoped=True,
            condition=condition,
            actions=[
                IncludeLaunchDescription(
                    spawn_source,
                    launch_arguments=launch_arguments.items(),
                )
            ],
        )

    default_spawn = make_spawn(
        spawn_launch,
        'warehouse',
        UnlessCondition(use_custom_sim),
    )
    custom_spawn = make_spawn(
        tour_spawn_launch,
        custom_world_name,
        IfCondition(use_custom_sim),
        {
            'controller_manager_timeout': LaunchConfiguration('controller_manager_timeout'),
            'controller_service_call_timeout': LaunchConfiguration(
                'controller_service_call_timeout'
            ),
            'controller_switch_timeout': LaunchConfiguration('controller_switch_timeout'),
            'controller_start_delay': LaunchConfiguration('controller_start_delay'),
            'robot_nodes_start_delay': LaunchConfiguration('robot_nodes_start_delay'),
        },
    )

    default_localization = IncludeLaunchDescription(
        localization_launch,
        condition=IfCondition(PythonExpression([
            "'", localization, "' == 'true' and '", use_custom_sim, "' == 'false'"
        ])),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
            'map': PathJoinSubstitution([
                turtlebot4_navigation,
                'maps',
                'warehouse.yaml',
            ]),
            'params': localization_params,
        }.items(),
    )

    custom_localization = IncludeLaunchDescription(
        localization_launch,
        condition=IfCondition(PythonExpression([
            "'", localization, "' == 'true' and '", use_custom_sim, "' == 'true'"
        ])),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
            'map': custom_map,
            'params': localization_params,
        }.items(),
    )

    slam_node = IncludeLaunchDescription(
        slam_launch,
        condition=IfCondition(slam),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
    )

    nav2_node = IncludeLaunchDescription(
        nav2_launch,
        condition=IfCondition(nav2),
        launch_arguments={
            'namespace': namespace,
            'use_sim_time': use_sim_time,
        }.items(),
    )

    initial_pose_publisher = TimerAction(
        period=12.0,
        actions=[
            Node(
                package='tourbot_bringup',
                executable='initial_pose_publisher',
                output='screen',
                parameters=[{
                    'frame_id': 'map',
                    'x': x,
                    'y': y,
                    'yaw': yaw,
                    'period': 1.0,
                    'count': 20,
                }],
                condition=IfCondition(localization),
            )
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Robot namespace',
        ),

        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use simulation time',
        ),

        DeclareLaunchArgument(
            'rviz',
            default_value='false',
            description='Launch RViz navigation view',
        ),

        DeclareLaunchArgument(
            'localization',
            default_value='false',
            description='Launch AMCL localization',
        ),

        DeclareLaunchArgument(
            'slam',
            default_value='false',
            description='Launch SLAM instead of map localization',
        ),

        DeclareLaunchArgument(
            'nav2',
            default_value='false',
            description='Launch Nav2 navigation stack',
        ),

        DeclareLaunchArgument(
            'model',
            default_value='lite',
            description='TurtleBot4 model: standard or lite',
        ),
        DeclareLaunchArgument(
            'gazebo_gui',
            default_value='true',
            description='Launch Gazebo GUI as a separate client for custom simulation',
        ),

        DeclareLaunchArgument(
            'use_custom_sim',
            default_value='true',
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
            'custom_world_name',
            default_value='cardboard_city',
            description='SDF world name used in Gazebo transport and ROS bridge topics',
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

        DeclareLaunchArgument(
            'localization_params',
            default_value=PathJoinSubstitution([
                tourbot_bringup,
                'config',
                'sim_localization.yaml',
            ]),
            description='AMCL localization parameters for simulation',
        ),

        DeclareLaunchArgument('x', default_value='0.0', description='Robot spawn x'),
        DeclareLaunchArgument('y', default_value='0.0', description='Robot spawn y'),
        DeclareLaunchArgument('z', default_value='0.0', description='Robot spawn z'),
        DeclareLaunchArgument('yaw', default_value='0.0', description='Robot spawn yaw'),
        DeclareLaunchArgument(
            'controller_manager_timeout',
            default_value='90',
            description='Seconds to wait for ros2_control controller manager services',
        ),
        DeclareLaunchArgument(
            'controller_service_call_timeout',
            default_value='45',
            description='Seconds to wait for each ros2_control service call response',
        ),
        DeclareLaunchArgument(
            'controller_switch_timeout',
            default_value='45',
            description='Seconds to allow controller activation in Gazebo',
        ),
        DeclareLaunchArgument(
            'controller_start_delay',
            default_value='10.0',
            description='Seconds to wait after robot spawn before loading controllers',
        ),
        DeclareLaunchArgument(
            'robot_nodes_start_delay',
            default_value='18.0',
            description='Seconds to wait after robot spawn before starting bridges and nodes',
        ),

        default_gazebo,
        custom_gz_resource_path,
        custom_gz_gui_plugin_path,
        custom_gazebo,
        custom_gazebo_gui,
        custom_clock_bridge,
        default_spawn,
        custom_spawn,
        default_localization,
        custom_localization,
        slam_node,
        nav2_node,
        initial_pose_publisher,
    ])
