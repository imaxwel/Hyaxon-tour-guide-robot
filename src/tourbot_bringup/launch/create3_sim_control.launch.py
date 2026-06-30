from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    LaunchConfiguration,
    NotEqualsSubstitution,
    PathJoinSubstitution,
)
from launch_ros.actions import Node


def generate_launch_description():
    pkg_create3_control = get_package_share_directory('irobot_create_control')

    namespace = LaunchConfiguration('namespace')
    manager_timeout = LaunchConfiguration('controller_manager_timeout')
    service_timeout = LaunchConfiguration('controller_service_call_timeout')
    switch_timeout = LaunchConfiguration('controller_switch_timeout')

    control_params_file = PathJoinSubstitution(
        [pkg_create3_control, 'config', 'control.yaml']
    )

    common_spawner_args = [
        '-c',
        'controller_manager',
        '--controller-manager-timeout',
        manager_timeout,
        '--service-call-timeout',
        service_timeout,
        '--switch-timeout',
        switch_timeout,
    ]

    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        namespace=namespace,
        arguments=[
            'joint_state_broadcaster',
            *common_spawner_args,
        ],
        output='screen',
    )

    diffdrive_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        namespace=namespace,
        arguments=[
            'diffdrive_controller',
            '--param-file',
            control_params_file,
            *common_spawner_args,
        ],
        output='screen',
    )

    diffdrive_after_joint_state = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[diffdrive_controller_spawner],
        )
    )

    tf_namespaced_odom_publisher = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_namespaced_odom_publisher',
        namespace=namespace,
        arguments=['0', '0', '0', '0', '0', '0', 'odom', [namespace, '/odom']],
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
        ],
        output='screen',
        condition=IfCondition(NotEqualsSubstitution(namespace, '')),
    )

    tf_namespaced_base_link_publisher = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_namespaced_base_link_publisher',
        namespace=namespace,
        arguments=[
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            [namespace, '/base_link'],
            'base_link',
        ],
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
        ],
        output='screen',
        condition=IfCondition(NotEqualsSubstitution(namespace, '')),
    )

    return LaunchDescription([
        DeclareLaunchArgument('namespace', default_value=''),
        DeclareLaunchArgument('controller_manager_timeout', default_value='90'),
        DeclareLaunchArgument('controller_service_call_timeout', default_value='45'),
        DeclareLaunchArgument('controller_switch_timeout', default_value='45'),
        joint_state_broadcaster_spawner,
        diffdrive_after_joint_state,
        tf_namespaced_odom_publisher,
        tf_namespaced_base_link_publisher,
    ])
