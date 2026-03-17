from io import BytesIO
import logging
import os
import random
import zipfile

from PIL import Image, ImageColor, ImageOps

from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)


class ImageUpload(BasePlugin):
    EPUB_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

    def _open_epub_image(self, path: str, dimensions: tuple, resize: bool = True) -> Image:
        """Extract a representative image from an ePub file."""
        if not zipfile.is_zipfile(path):
            raise RuntimeError("Uploaded ePub file is not valid.")

        with zipfile.ZipFile(path, "r") as epub_zip:
            image_candidates = []
            for file_info in epub_zip.infolist():
                file_name = file_info.filename
                if file_info.is_dir() or file_name.startswith("__MACOSX"):
                    continue

                lower_name = file_name.lower()
                if not lower_name.endswith(self.EPUB_IMAGE_EXTENSIONS):
                    continue

                # Prefer cover-like names, otherwise use largest image
                priority = 0 if "cover" in lower_name else 1
                image_candidates.append((priority, file_info.file_size, file_name))

            if not image_candidates:
                raise RuntimeError("No images found in the uploaded ePub file.")

            image_candidates.sort(key=lambda item: (item[0], -item[1]))
            selected_image = image_candidates[0][2]
            logger.info(f"Using image '{selected_image}' from ePub file")

            with epub_zip.open(selected_image) as image_stream:
                image_data = BytesIO(image_stream.read())

        image = self.image_loader.from_bytesio(image_data, dimensions, resize=resize)
        if not image:
            raise RuntimeError("Failed to load image from ePub file")

        return image

    def open_image(self, img_index: int, image_locations: list, dimensions: tuple, resize: bool = True) -> Image:
        """
        Open image with adaptive loader for memory efficiency.

        Args:
            img_index: Index of image to load
            image_locations: List of image paths
            dimensions: Target dimensions
            resize: Whether to auto-resize (set False if manual padding needed)
        """
        if not image_locations:
            raise RuntimeError("No images provided.")

        try:
            image_path = image_locations[img_index]
            extension = os.path.splitext(image_path)[1].lower()

            if extension == ".epub":
                image = self._open_epub_image(image_path, dimensions, resize=resize)
            else:
                image = self.image_loader.from_file(image_path, dimensions, resize=resize)

            if not image:
                raise RuntimeError("Failed to load image from file")
            return image
        except Exception as e:
            logger.error(f"Failed to read image file: {str(e)}")
            raise RuntimeError("Failed to read image file.")

    def generate_image(self, settings, device_config) -> Image:
        logger.info("=== Image Upload Plugin: Starting image generation ===")

        # Get the current index from the device json
        img_index = settings.get("image_index", 0)
        image_locations = settings.get("imageFiles[]")

        if not image_locations:
            logger.error("No images uploaded")
            raise RuntimeError("No images provided.")

        logger.debug(f"Total uploaded images: {len(image_locations)}")
        logger.debug(f"Current index: {img_index}")

        if img_index >= len(image_locations):
            # Prevent Index out of range issues when file list has changed
            logger.warning(f"Index {img_index} out of range, resetting to 0")
            img_index = 0

        # Get dimensions
        dimensions = device_config.get_resolution()
        orientation = device_config.get_config("orientation")
        if orientation == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        # Determine if we need manual padding
        needs_padding = settings.get('padImage') == "true"
        is_random = settings.get('randomize') == "true"
        background_option = settings.get('backgroundOption', 'blur')
        image_width = int(settings.get("displayWidth") or 0)
        image_height = int(settings.get("displayHeight") or 0)

        logger.debug(
            f"Settings: randomize={is_random}, pad_image={needs_padding}, "
            f"background_option={background_option}, display_width={image_width}, display_height={image_height}"
        )

        # Load image (without auto-resize if padding needed)
        if is_random:
            img_index = random.randrange(0, len(image_locations))
            logger.info(f"Random mode: Selected image index {img_index}")
            image = self.open_image(img_index, image_locations, dimensions, resize=not needs_padding)
        else:
            logger.info(f"Sequential mode: Loading image index {img_index}")
            image = self.open_image(img_index, image_locations, dimensions, resize=not needs_padding)
            img_index = (img_index + 1) % len(image_locations)
            logger.debug(f"Next index will be: {img_index}")

        # Write the new index back to the device json
        settings['image_index'] = img_index

        # Apply padding if requested
        if needs_padding:
            logger.debug(f"Applying padding with {background_option} background")
            if background_option == "blur":
                image = pad_image_blur(image, dimensions)
            else:
                background_color = ImageColor.getcolor(settings.get('backgroundColor') or "white", image.mode)
                image = ImageOps.pad(image, dimensions, color=background_color, method=Image.Resampling.LANCZOS)

        if image_width > 0 and image_height > 0:
            target_size = (min(image_width, dimensions[0]), min(image_height, dimensions[1]))
            logger.info(f"Applying custom display size: {target_size[0]}x{target_size[1]}")
            resized_image = ImageOps.contain(image, target_size, method=Image.Resampling.LANCZOS)

            background_color = ImageColor.getcolor(settings.get("backgroundColor") or "white", resized_image.mode)
            centered_image = Image.new(resized_image.mode, dimensions, background_color)
            offset = ((dimensions[0] - resized_image.width) // 2, (dimensions[1] - resized_image.height) // 2)
            centered_image.paste(resized_image, offset)
            image = centered_image

        logger.info("=== Image Upload Plugin: Image generation complete ===")
        return image

    def cleanup(self, settings):
        """Delete all uploaded image files associated with this plugin instance."""
        image_locations = settings.get("imageFiles[]", [])
        if not image_locations:
            return

        for image_path in image_locations:
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Deleted uploaded image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete uploaded image {image_path}: {e}")
