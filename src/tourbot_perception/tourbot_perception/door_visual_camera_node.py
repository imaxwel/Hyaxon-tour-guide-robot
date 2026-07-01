from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from apriltag_msgs.msg import AprilTagDetectionArray
from PIL import Image as PilImage
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool


class DoorVisualCameraNode(Node):
    """Publish a deterministic door camera stream for AprilTag-in-the-loop demos."""

    def __init__(self) -> None:
        super().__init__("door_visual_camera_node")

        self.declare_parameter("tag_id", 1)
        self.declare_parameter("tag_texture_path", "")
        self.declare_parameter("tag_visible_topic", "/door_demo/tag_visible")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("image_topic", "/oakd/rgb/preview/image_raw")
        self.declare_parameter("camera_info_topic", "/oakd/rgb/preview/camera_info")
        self.declare_parameter(
            "visualization_image_topic",
            "/door_demo/visualization/image_raw",
        )
        self.declare_parameter("frame_id", "oakd_rgb_camera_optical_frame")
        self.declare_parameter("image_width", 640)
        self.declare_parameter("image_height", 480)
        self.declare_parameter("fps", 12.0)
        self.declare_parameter("tag_pixel_size", 190)

        self.tag_id = int(self.get_parameter("tag_id").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.width = int(self.get_parameter("image_width").value)
        self.height = int(self.get_parameter("image_height").value)
        self.fps = float(self.get_parameter("fps").value)
        self.tag_pixel_size = int(self.get_parameter("tag_pixel_size").value)

        self.tag_visible = True
        self.latest_detections = AprilTagDetectionArray()
        self.tag_texture = self.load_tag_texture()

        self.image_pub = self.create_publisher(
            Image,
            str(self.get_parameter("image_topic").value),
            10,
        )
        self.camera_info_pub = self.create_publisher(
            CameraInfo,
            str(self.get_parameter("camera_info_topic").value),
            10,
        )
        self.visualization_pub = self.create_publisher(
            Image,
            str(self.get_parameter("visualization_image_topic").value),
            10,
        )
        self.create_subscription(
            Bool,
            str(self.get_parameter("tag_visible_topic").value),
            self.tag_visible_callback,
            10,
        )
        self.create_subscription(
            AprilTagDetectionArray,
            str(self.get_parameter("detections_topic").value),
            self.detections_callback,
            10,
        )

        timer_period = 1.0 / max(self.fps, 1.0)
        self.create_timer(timer_period, self.publish_frame)

        self.get_logger().info(
            "Publishing visual door camera: detector image, camera_info, "
            "and annotated UI image."
        )

    def load_tag_texture(self) -> np.ndarray:
        configured_path = str(self.get_parameter("tag_texture_path").value).strip()

        if configured_path:
            texture_path = Path(configured_path)
        else:
            bringup_share = Path(get_package_share_directory("tourbot_bringup"))
            tag_name = f"tag36_11_{self.tag_id:05d}"
            texture_path = (
                bringup_share
                / "worlds"
                / "cardboard_city"
                / "models"
                / tag_name
                / "materials"
                / "textures"
                / f"{tag_name}.png"
            )

        if not texture_path.exists():
            raise FileNotFoundError(f"AprilTag texture not found: {texture_path}")

        tag = PilImage.open(texture_path).convert("RGB")
        tag = tag.resize(
            (self.tag_pixel_size, self.tag_pixel_size),
            resample=PilImage.Resampling.NEAREST,
        )
        return np.array(tag, dtype=np.uint8)

    def tag_visible_callback(self, msg: Bool) -> None:
        self.tag_visible = bool(msg.data)

    def detections_callback(self, msg: AprilTagDetectionArray) -> None:
        self.latest_detections = msg

    def make_camera_info(self, stamp) -> CameraInfo:
        msg = CameraInfo()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.width = self.width
        msg.height = self.height
        fx = 525.0
        fy = 525.0
        cx = self.width / 2.0
        cy = self.height / 2.0
        msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        return msg

    def make_image_msg(self, stamp, frame: np.ndarray) -> Image:
        frame = np.ascontiguousarray(frame)
        msg = Image()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.height = int(frame.shape[0])
        msg.width = int(frame.shape[1])
        msg.encoding = "rgb8"
        msg.is_bigendian = False
        msg.step = int(frame.shape[1] * 3)
        msg.data = frame.tobytes()
        return msg

    def draw_tag(self, frame: np.ndarray, center_x: int, center_y: int) -> None:
        size = self.tag_pixel_size
        pad = 10
        x0 = int(center_x - size / 2)
        y0 = int(center_y - size / 2)
        x1 = x0 + size
        y1 = y0 + size

        cv2.rectangle(
            frame,
            (x0 - pad, y0 - pad),
            (x1 + pad, y1 + pad),
            (255, 255, 255),
            thickness=-1,
        )
        frame[y0:y1, x0:x1, :] = self.tag_texture

    def render_detector_frame(self) -> np.ndarray:
        frame = np.full((self.height, self.width, 3), (232, 229, 220), dtype=np.uint8)

        # Back wall and doorway geometry make the image readable without adding
        # text to the detector input.
        cv2.rectangle(frame, (0, 0), (self.width, self.height), (226, 222, 212), -1)
        cv2.rectangle(frame, (205, 60), (435, 420), (145, 117, 82), -1)
        cv2.rectangle(frame, (235, 90), (405, 395), (112, 92, 66), 3)
        cv2.rectangle(frame, (0, 390), (self.width, self.height), (194, 188, 172), -1)

        if self.tag_visible:
            self.draw_tag(frame, self.width // 2, 220)
        else:
            cv2.rectangle(frame, (250, 85), (390, 400), (72, 95, 83), -1)
            cv2.rectangle(frame, (120, 105), (250, 405), (145, 117, 82), -1)

        return frame

    def detection_ids(self) -> list[int]:
        return [int(detection.id) for detection in self.latest_detections.detections]

    def draw_text(
        self,
        frame: np.ndarray,
        text: str,
        origin: tuple[int, int],
        color: tuple[int, int, int],
        scale: float = 0.62,
        thickness: int = 2,
    ) -> None:
        cv2.putText(
            frame,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    def draw_detection_overlay(self, frame: np.ndarray) -> None:
        for detection in self.latest_detections.detections:
            if len(detection.corners) < 4:
                continue

            points = np.array(
                [(int(point.x), int(point.y)) for point in detection.corners],
                dtype=np.int32,
            )
            cv2.polylines(frame, [points], True, (35, 210, 75), 3)
            cv2.circle(
                frame,
                (int(detection.centre.x), int(detection.centre.y)),
                5,
                (255, 64, 64),
                -1,
            )
            self.draw_text(
                frame,
                f"detected id={int(detection.id)}",
                (int(detection.centre.x) - 70, int(detection.centre.y) - 115),
                (35, 210, 75),
                scale=0.55,
            )

    def render_visualization_frame(self, detector_frame: np.ndarray) -> np.ndarray:
        frame = detector_frame.copy()
        if self.tag_visible:
            visible_text = "DOOR CLOSED - tag visible"
            banner_color = (118, 76, 36)
        else:
            visible_text = "DOOR OPEN - tag removed"
            banner_color = (44, 124, 82)

        cv2.rectangle(frame, (0, 0), (self.width, 48), banner_color, -1)
        self.draw_text(frame, visible_text, (18, 31), (255, 255, 255), scale=0.72)

        ids = self.detection_ids()
        detector_text = f"apriltag_ros /detections ids={ids}"
        self.draw_text(frame, detector_text, (18, self.height - 24), (30, 30, 30))
        self.draw_detection_overlay(frame)
        return frame

    def publish_frame(self) -> None:
        stamp = self.get_clock().now().to_msg()
        detector_frame = self.render_detector_frame()
        visualization_frame = self.render_visualization_frame(detector_frame)

        self.image_pub.publish(self.make_image_msg(stamp, detector_frame))
        self.camera_info_pub.publish(self.make_camera_info(stamp))
        self.visualization_pub.publish(
            self.make_image_msg(stamp, visualization_frame)
        )


def main(args: Iterable[str] | None = None) -> None:
    rclpy.init(args=args)
    node = DoorVisualCameraNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
