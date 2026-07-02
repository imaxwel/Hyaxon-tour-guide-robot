from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    tag_id = LaunchConfiguration("tag_id")
    use_sim_time = LaunchConfiguration("use_sim_time")
    world_name = LaunchConfiguration("world_name")
    start_delay_sec = LaunchConfiguration("start_delay_sec")
    start_image_view = LaunchConfiguration("start_image_view")
    visible_before_open_sec = LaunchConfiguration("visible_before_open_sec")
    missing_duration_sec = LaunchConfiguration("missing_duration_sec")
    door_forward_distance = LaunchConfiguration("door_forward_distance")
    door_forward_speed = LaunchConfiguration("door_forward_speed")
    set_initial_robot_pose = LaunchConfiguration("set_initial_robot_pose")
    initial_robot_x = LaunchConfiguration("initial_robot_x")
    initial_robot_y = LaunchConfiguration("initial_robot_y")
    initial_robot_z = LaunchConfiguration("initial_robot_z")
    initial_robot_yaw = LaunchConfiguration("initial_robot_yaw")

    tourbot_perception = FindPackageShare("tourbot_perception")
    apriltag_config = PathJoinSubstitution(
        [tourbot_perception, "config", "apriltags_36h11_gazebo.yaml"]
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

    door_state_controller = Node(
        package="tourbot_bringup",
        executable="door_state_gazebo_controller",
        name="door_state_gazebo_controller",
        output="screen",
        parameters=[
            {
                "use_sim_time": False,
                "tag_id": tag_id,
                "world_name": world_name,
            }
        ],
    )

    align_to_apriltag_server = Node(
        package="tourbot_behaviors",
        executable="align_to_apriltag_server",
        name="align_to_apriltag_server",
        output="screen",
        parameters=[
            {
                "use_sim_time": False,
                "cmd_vel_topic": "/diffdrive_controller/cmd_vel",
                "use_zero_cmd_stamp": True,
            }
        ],
    )

    wait_for_tag_removed_server = Node(
        package="tourbot_behaviors",
        executable="wait_for_tag_removed_server",
        name="wait_for_tag_removed_server",
        output="screen",
        parameters=[{"use_sim_time": False}],
    )

    door_behavior_server = Node(
        package="tourbot_behaviors",
        executable="door_behavior_server",
        name="door_behavior_server",
        output="screen",
        parameters=[
            {
                "use_sim_time": False,
                "odom_topic": "/sim_ground_truth_pose",
                "cmd_vel_topic": "/diffdrive_controller/cmd_vel",
                "use_zero_cmd_stamp": True,
                "odom_wait_timeout_sec": 5.0,
                # Use Gazebo ground-truth pose for demo-only guards; the
                # lightweight spawn moves the model through Gazebo cmd_vel and
                # does not rely on diffdrive /odom for this open-loop behavior.
                "enforce_workspace_bounds": True,
                "workspace_min_x": -0.45,
                "workspace_max_x": 4.15,
                "workspace_min_y": -1.20,
                "workspace_max_y": 1.20,
                "max_lateral_drift": 0.35,
                "max_linear_motion_sec": 90.0,
                "linear_stall_timeout_sec": 20.0,
                "linear_stall_min_progress": 0.01,
                "stop_command_repeats": 8,
                "stop_command_period_sec": 0.05,
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
                "use_sim_time": False,
                "tag_id": tag_id,
                "publish_demo_odom": False,
                "publish_synthetic_detections": False,
                "publish_camera_info": False,
                "start_delay_sec": start_delay_sec,
                "wait_for_initial_detection_sec": 25.0,
                "visible_before_open_sec": visible_before_open_sec,
                "missing_duration_sec": missing_duration_sec,
                "wait_timeout_sec": 20.0,
                "align_timeout_sec": 20.0,
                "x_tolerance_px": 12.0,
                "door_wait_seconds": 0.5,
                "door_forward_distance": door_forward_distance,
                "door_forward_speed": door_forward_speed,
            }
        ],
    )

    image_view = Node(
        package="image_view",
        executable="image_view",
        name="gazebo_oakd_image_view",
        output="screen",
        condition=IfCondition(start_image_view),
        remappings=[
            ("image", "/oakd/rgb/preview/image_raw"),
        ],
    )

    initial_robot_pose_setter = Node(
        package="tourbot_bringup",
        executable="gazebo_entity_pose_setter",
        name="gazebo_demo_initial_robot_pose",
        output="screen",
        condition=IfCondition(set_initial_robot_pose),
        parameters=[
            {
                "world_name": world_name,
                "entity_name": "turtlebot4",
                "x": initial_robot_x,
                "y": initial_robot_y,
                "z": initial_robot_z,
                "yaw": initial_robot_yaw,
                "service_timeout_ms": 3000,
                "repeat_count": 12,
                "repeat_period_sec": 0.5,
            }
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
                description="Use /clock from Gazebo.",
            ),
            DeclareLaunchArgument(
                "world_name",
                default_value="world_demo",
                description="Gazebo world name used by gz services and bridge topics.",
            ),
            DeclareLaunchArgument(
                "start_delay_sec",
                default_value="6.0",
                description="Delay inside the demo node before sending action goals.",
            ),
            DeclareLaunchArgument(
                "start_image_view",
                default_value="false",
                description="Open image_view for the Gazebo OAK-D RGB stream.",
            ),
            DeclareLaunchArgument(
                "visible_before_open_sec",
                default_value="2.0",
                description="How long to keep the door tag visible before opening.",
            ),
            DeclareLaunchArgument(
                "missing_duration_sec",
                default_value="1.0",
                description="Required continuous no-tag duration before traversal.",
            ),
            DeclareLaunchArgument(
                "door_forward_distance",
                default_value="0.60",
                description="Forward distance used by the door traversal action.",
            ),
            DeclareLaunchArgument(
                "door_forward_speed",
                default_value="0.16",
                description="Forward speed used by the door traversal action.",
            ),
            DeclareLaunchArgument(
                "set_initial_robot_pose",
                default_value="true",
                description=(
                    "Set turtlebot4 to the default door observation pose. "
                    "Keep true for the two-terminal Gazebo demo."
                ),
            ),
            DeclareLaunchArgument(
                "initial_robot_x",
                default_value="3.14",
                description="Initial robot x pose for the Gazebo door demo.",
            ),
            DeclareLaunchArgument(
                "initial_robot_y",
                default_value="0.0",
                description="Initial robot y pose for the Gazebo door demo.",
            ),
            DeclareLaunchArgument(
                "initial_robot_z",
                default_value="0.0",
                description="Initial robot z pose for the Gazebo door demo.",
            ),
            DeclareLaunchArgument(
                "initial_robot_yaw",
                default_value="-1.5708",
                description="Initial robot yaw facing the tag 1 outward door.",
            ),
            apriltag_detector,
            door_state_controller,
            image_view,
            TimerAction(period=0.5, actions=[initial_robot_pose_setter]),
            align_to_apriltag_server,
            wait_for_tag_removed_server,
            door_behavior_server,
            TimerAction(period=2.0, actions=[door_apriltag_demo_node]),
        ]
    )
