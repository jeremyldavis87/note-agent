from __future__ import annotations

from typing import Callable, List, Optional, Tuple, TypeVar

import cv2
import numpy as np

T = TypeVar('T')


def _rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    """
    Rotate an image by the specified angle.
    
    Args:
        image: Image to rotate (BGR or grayscale)
        angle: Rotation angle in degrees (0, 90, 180, or 270)
        
    Returns:
        Rotated image (or original if angle is 0)
    """
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    elif angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        return image


def _try_detection_with_rotations(
    image: np.ndarray,
    detection_func: Callable[[np.ndarray], Optional[T]],
    angles: Tuple[int, ...] = (0, 90, 180, 270)
) -> Optional[T]:
    """
    Try detection on an image with multiple rotations.
    
    Args:
        image: Image to process
        detection_func: Function that takes an image and returns a result or None
        angles: Tuple of rotation angles to try (default: 0, 90, 180, 270)
        
    Returns:
        First successful detection result, or None if all attempts fail
    """
    for angle in angles:
        rotated = _rotate_image(image, angle)
        result = detection_func(rotated)
        if result is not None:
            return result
    return None


def _detect_qr_opencv(bgr_image: np.ndarray) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    """
    Detect QR codes using OpenCV's QRCodeDetector (primary method).
    
    Args:
        bgr_image: BGR image (can be grayscale or color)
        
    Returns:
        List of tuples: (qr_data, (x, y, w, h))
    """
    try:
        detector = cv2.QRCodeDetector()
    except AttributeError:
        # QRCodeDetector not available (shouldn't happen with opencv-contrib-python)
        return []
    
    results = []
    
    # Convert to grayscale if needed
    if len(bgr_image.shape) == 3:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr_image.copy()
    
    # Try detectAndDecodeMulti first (handles multiple QR codes)
    retval, decoded_info, points, straight_qrcode = detector.detectAndDecodeMulti(gray)
    
    if retval and decoded_info:
        for i, data in enumerate(decoded_info):
            if data and len(data.strip()) > 0:
                # Get bounding box from points
                if points is not None and i < len(points):
                    pts = points[i]
                    if pts is not None and len(pts) > 0:
                        # Calculate bounding box from corner points
                        x_coords = [int(p[0]) for p in pts]
                        y_coords = [int(p[1]) for p in pts]
                        x = min(x_coords)
                        y = min(y_coords)
                        w = max(x_coords) - x
                        h = max(y_coords) - y
                        results.append((data, (x, y, w, h)))
    
    # If detectMulti didn't find anything, try single detection
    if not results:
        data, bbox, _ = detector.detectAndDecode(gray)
        if data and len(data.strip()) > 0 and bbox is not None:
            # bbox is a 2x4 array of corner points
            x_coords = [int(p[0]) for p in bbox[0]]
            y_coords = [int(p[1]) for p in bbox[0]]
            x = min(x_coords)
            y = min(y_coords)
            w = max(x_coords) - x
            h = max(y_coords) - y
            results.append((data, (x, y, w, h)))
    
    return results


def _detect_datamatrix_pylibdmtx(bgr_image: np.ndarray) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    """
    Detect Data Matrix codes using pylibdmtx.
    
    Args:
        bgr_image: BGR image (can be grayscale or color)
        
    Returns:
        List of tuples: (datamatrix_data, (x, y, w, h))
    """
    try:
        from pylibdmtx import pylibdmtx  # type: ignore
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        error_msg = str(e)
        if "Unable to find dmtx shared library" in error_msg or "dmtx" in error_msg.lower():
            logger.debug(
                "pylibdmtx requires the libdmtx library to be installed. "
                "On Ubuntu 24.04, install it with: sudo apt-get install libdmtx0t64 "
                "(or libdmtx1 on older systems)"
            )
        return []
    
    results = []
    
    # Convert to grayscale if needed
    if len(bgr_image.shape) == 3:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr_image.copy()
    
    # Convert to PIL Image format that pylibdmtx expects
    try:
        from PIL import Image
        pil_image = Image.fromarray(gray)
    except ImportError:
        return []
    
    # Decode Data Matrix codes
    try:
        decoded = pylibdmtx.decode(pil_image)
        for d in decoded:
            if d and d.data:
                try:
                    data = d.data.decode("utf-8")
                    if data and len(data.strip()) > 0:
                        # Get bounding box from decoded result
                        # pylibdmtx returns rect (left, top, width, height)
                        rect = d.rect
                        if rect:
                            x, y, w, h = rect.left, rect.top, rect.width, rect.height
                            results.append((data, (x, y, w, h)))
                        else:
                            # If no rect, use a default size or skip
                            results.append((data, (0, 0, 0, 0)))
                except (UnicodeDecodeError, AttributeError):
                    continue
    except Exception:
        # Silent fail - return empty list
        pass
    
    return results


def detect_qr_positions(bgr) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    """
    Detect QR codes and Data Matrix codes in a full image and return their data and positions.
    Uses OpenCV QRCodeDetector as primary method for QR codes, pylibdmtx for Data Matrix codes,
    falls back to pyzbar for QR codes.
    
    Args:
        bgr: BGR image
        
    Returns:
        List of tuples: (code_data, (x, y, w, h)) - can contain both QR and Data Matrix codes
    """
    all_results = []
    
    # Try OpenCV QRCodeDetector first (primary method for QR codes)
    preprocessed_variants = _preprocess_for_qr(bgr)
    
    # Try original and preprocessed variants
    images_to_try = [bgr] + preprocessed_variants
    
    for img in images_to_try:
        # Try different rotations
        for angle in (0, 90, 180, 270):
            rot = _rotate_image(img, angle)
            
            # Try QR code detection
            qr_results = _detect_qr_opencv(rot)
            if qr_results:
                all_results.extend(qr_results)
            
            # Try Data Matrix detection
            dm_results = _detect_datamatrix_pylibdmtx(rot)
            if dm_results:
                all_results.extend(dm_results)
            
            if all_results:
                # Found codes - return immediately
                return all_results
    
    # Also try Data Matrix on all variants before falling back
    for img in images_to_try:
        for angle in (0, 90, 180, 270):
            rot = _rotate_image(img, angle)
            
            dm_results = _detect_datamatrix_pylibdmtx(rot)
            if dm_results:
                all_results.extend(dm_results)
                if all_results:
                    return all_results
    
    # Fallback to pyzbar if OpenCV and Data Matrix didn't find anything
    try:
        from pyzbar.pyzbar import decode, ZBarSymbol  # type: ignore
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        error_msg = str(e)
        if "Unable to find zbar shared library" in error_msg or "zbar" in error_msg.lower():
            logger.debug(
                "pyzbar requires the zbar library to be installed. "
                "On Ubuntu/Debian, install it with: sudo apt-get install libzbar0t64 "
                "(or libzbar0 on older systems). Falling back to OpenCV only."
            )
        return []
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"pyzbar import failed: {e}, using OpenCV only")
        return []

    results = []
    
    # Try multiple preprocessing variants with pyzbar
    images_to_try = []
    
    # Convert to grayscale if needed
    if len(bgr.shape) == 3:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        images_to_try.append(("bgr", bgr))
    else:
        gray = bgr.copy()
        images_to_try.append(("gray", gray))
    
    images_to_try.append(("gray", gray))
    
    # Denoised
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    images_to_try.append(("denoised", denoised))
    
    # Adaptive threshold
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    images_to_try.append(("adaptive", adaptive))
    
    # Histogram equalization
    equalized = cv2.equalizeHist(denoised)
    images_to_try.append(("equalized", equalized))
    
    # Try each preprocessing variant with rotations
    for img_name, img in images_to_try:
        for angle in (0, 90, 180, 270):
            rot = _rotate_image(img, angle)
                
            try:
                # Try QRCODE first, then all symbols if that fails
                decoded = decode(rot, symbols=[ZBarSymbol.QRCODE])
                if not decoded:
                    # Try all symbol types as fallback
                    decoded = decode(rot)
            except Exception:
                continue
                
            for d in decoded:
                # Only process QR codes
                if d.type != 'QRCODE':
                    continue
                x, y, w, h = d.rect
                try:
                    qr_data = d.data.decode("utf-8")
                    results.append((qr_data, (x, y, w, h)))
                except (UnicodeDecodeError, AttributeError):
                    continue
                    
            if results:
                # Found QR codes, add to all results
                all_results.extend(results)
    
    # Return all results (QR codes from pyzbar + any Data Matrix codes found)
    if all_results:
        return all_results
    
    return []


def _detect_datamatrix_in_region(bgr_region: np.ndarray) -> Optional[Tuple[str, str, Tuple[int, int]]]:
    """
    Detect a single Data Matrix code in a region using pylibdmtx.
    
    Args:
        bgr_region: Cropped BGR image of a single note region
        
    Returns:
        Tuple of (position_string, datamatrix_data, (center_x, center_y)) or None
    """
    try:
        from pylibdmtx import pylibdmtx  # type: ignore
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        error_msg = str(e)
        if "Unable to find dmtx shared library" in error_msg or "dmtx" in error_msg.lower():
            logger.debug(
                "pylibdmtx requires the libdmtx library to be installed. "
                "On Ubuntu 24.04, install it with: sudo apt-get install libdmtx0t64 "
                "(or libdmtx1 on older systems)"
            )
        return None
    
    h, w = bgr_region.shape[:2]
    
    # Convert to grayscale if needed
    if len(bgr_region.shape) == 3:
        gray = cv2.cvtColor(bgr_region, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr_region.copy()
    
    # Convert to PIL Image format
    try:
        from PIL import Image
        pil_image = Image.fromarray(gray)
    except ImportError:
        return None
    
    # Decode Data Matrix codes
    try:
        decoded = pylibdmtx.decode(pil_image)
        if decoded:
            # Take first Data Matrix code found
            d = decoded[0]
            if d and d.data:
                try:
                    data = d.data.decode("utf-8")
                    if data and len(data.strip()) > 0:
                        # Get bounding box
                        rect = d.rect
                        if rect:
                            qr_x = rect.left
                            qr_y = rect.top
                            qr_w = rect.width
                            qr_h = rect.height
                        else:
                            return None
                        
                        # Calculate center
                        qr_center_x = qr_x + qr_w // 2
                        qr_center_y = qr_y + qr_h // 2
                        
                        # Determine position
                        is_left = qr_center_x < w / 2
                        is_top = qr_center_y < h / 2
                        
                        if is_top and is_left:
                            position = "top_left"
                        elif is_top and not is_left:
                            position = "top_right"
                        elif not is_top and is_left:
                            position = "bottom_left"
                        else:
                            position = "bottom_right"
                        
                        return (position, data, (qr_center_x, qr_center_y))
                except (UnicodeDecodeError, AttributeError):
                    pass
    except Exception:
        pass
    
    return None


def _detect_qr_opencv_in_region(bgr_region: np.ndarray) -> Optional[Tuple[str, str, Tuple[int, int]]]:
    """
    Detect a single QR code in a region using OpenCV's QRCodeDetector.
    
    Args:
        bgr_region: Cropped BGR image of a single note region
        
    Returns:
        Tuple of (position_string, qr_code_data, (qr_center_x, qr_center_y)) or None
    """
    try:
        detector = cv2.QRCodeDetector()
    except AttributeError:
        return None
    
    h, w = bgr_region.shape[:2]
    
    # Convert to grayscale if needed
    if len(bgr_region.shape) == 3:
        gray = cv2.cvtColor(bgr_region, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr_region.copy()
    
    # Try detectAndDecode first (single QR code)
    data, bbox, _ = detector.detectAndDecode(gray)
    
    if data and len(data.strip()) > 0 and bbox is not None:
        # bbox is a 2x4 array of corner points
        x_coords = [int(p[0]) for p in bbox[0]]
        y_coords = [int(p[1]) for p in bbox[0]]
        qr_x = min(x_coords)
        qr_y = min(y_coords)
        qr_w = max(x_coords) - qr_x
        qr_h = max(y_coords) - qr_y
        
        # Calculate center
        qr_center_x = qr_x + qr_w // 2
        qr_center_y = qr_y + qr_h // 2
        
        # Determine position
        is_left = qr_center_x < w / 2
        is_top = qr_center_y < h / 2
        
        if is_top and is_left:
            position = "top_left"
        elif is_top and not is_left:
            position = "top_right"
        elif not is_top and is_left:
            position = "bottom_left"
        else:
            position = "bottom_right"
        
        return (position, data, (qr_center_x, qr_center_y))
    
    # Try detectAndDecodeMulti as fallback
    retval, decoded_info, points, straight_qrcode = detector.detectAndDecodeMulti(gray)
    
    if retval and decoded_info:
        # Take first QR code found
        for i, qr_data in enumerate(decoded_info):
            if qr_data and len(qr_data.strip()) > 0:
                if points is not None and i < len(points):
                    pts = points[i]
                    if pts is not None and len(pts) > 0:
                        x_coords = [int(p[0]) for p in pts]
                        y_coords = [int(p[1]) for p in pts]
                        qr_x = min(x_coords)
                        qr_y = min(y_coords)
                        qr_w = max(x_coords) - qr_x
                        qr_h = max(y_coords) - qr_y
                        
                        qr_center_x = qr_x + qr_w // 2
                        qr_center_y = qr_y + qr_h // 2
                        
                        # Determine position
                        is_left = qr_center_x < w / 2
                        is_top = qr_center_y < h / 2
                        
                        if is_top and is_left:
                            position = "top_left"
                        elif is_top and not is_left:
                            position = "top_right"
                        elif not is_top and is_left:
                            position = "bottom_left"
                        else:
                            position = "bottom_right"
                        
                        return (position, qr_data, (qr_center_x, qr_center_y))
    
    return None


def _preprocess_for_qr(bgr_image: np.ndarray) -> List[np.ndarray]:
    """
    Preprocess image for better QR code detection.
    Returns multiple preprocessing variants to try.
    """
    variants = []
    
    # Convert to grayscale if needed
    if len(bgr_image.shape) == 3:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr_image.copy()
    
    # Original grayscale
    variants.append(gray)
    
    # Denoised
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    variants.append(denoised)
    
    # Adaptive threshold
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(adaptive)
    
    # Histogram equalization
    equalized = cv2.equalizeHist(denoised)
    variants.append(equalized)
    
    # Upscale if image is small (QR codes might be too small)
    h, w = gray.shape[:2]
    if h < 400 or w < 400:
        # Scale up by 2x
        upscaled = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        variants.append(upscaled)
        
        upscaled_denoised = cv2.fastNlMeansDenoising(upscaled, h=10)
        variants.append(upscaled_denoised)
    
    return variants


def detect_qr_in_region(
    bgr_region, threshold_pixels: int = 50
) -> Optional[Tuple[str, Optional[str], Tuple[int, int]]]:
    """
    Detect QR code or Data Matrix code in a cropped note region and determine its position and decode its data.
    Uses OpenCV QRCodeDetector as primary method for QR codes, pylibdmtx for Data Matrix codes,
    falls back to pyzbar for QR codes.
    
    Args:
        bgr_region: Cropped BGR image of a single note region
        threshold_pixels: Minimum distance from edges to consider code position (default: 50)
        
    Returns:
        Tuple of (position_string, code_data, (code_center_x, code_center_y)) or None if no code found.
        position_string is one of: 'top_left', 'top_right', 'bottom_left', 'bottom_right'
        code_data is the decoded UTF-8 string from the QR code or Data Matrix code
    """
    h, w = bgr_region.shape[:2]
    
    # Preprocess for better code detection
    preprocessed_variants = _preprocess_for_qr(bgr_region)
    
    # Original BGR converted to grayscale
    if len(bgr_region.shape) == 3:
        gray_original = cv2.cvtColor(bgr_region, cv2.COLOR_BGR2GRAY)
    else:
        gray_original = bgr_region.copy()
    
    all_images = [bgr_region, gray_original] + preprocessed_variants
    
    # Try OpenCV QRCodeDetector first (primary method for QR codes)
    for img in all_images:
        for angle in (0, 90, 180, 270):
            rot = _rotate_image(img, angle)
            
            # Try QR code detection
            result = _detect_qr_opencv_in_region(rot)
            if result:
                # If rotated, we need to map coordinates back to original
                # For now, return the result (coordinate mapping can be improved if needed)
                position, qr_data, (center_x, center_y) = result
                return (position, qr_data, (center_x, center_y))
            
            # Try Data Matrix detection
            dm_result = _detect_datamatrix_in_region(rot)
            if dm_result:
                position, dm_data, (center_x, center_y) = dm_result
                return (position, dm_data, (center_x, center_y))
    
    # Fallback to pyzbar if OpenCV didn't find anything
    try:
        from pyzbar.pyzbar import decode, ZBarSymbol  # type: ignore
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        error_msg = str(e)
        if "Unable to find zbar shared library" in error_msg or "zbar" in error_msg.lower():
            logger.debug(
                "pyzbar requires the zbar library to be installed. "
                "On Ubuntu/Debian, install it with: sudo apt-get install libzbar0t64 "
                "(or libzbar0 on older systems). Falling back to OpenCV only."
            )
        return None
    except Exception:
        return None

    # Try original and all preprocessing variants with different rotations for pyzbar
    images_to_try = []
    
    for img in all_images:
        for angle in (0, 90, 180, 270):
            images_to_try.append((img, angle))
    
    for img, angle in images_to_try:
        rot = _rotate_image(img, angle)
            
        try:
            # Try QRCODE first, then all symbols if that fails
            decoded = decode(rot, symbols=[ZBarSymbol.QRCODE])
            if not decoded:
                decoded = decode(rot)
        except Exception:
            # Skip this image variant if decode fails
            continue
            
        if decoded:
            # Take first QR code found
            d = decoded[0]
            
            # Check if data exists
            if not hasattr(d, 'data') or not d.data:
                continue
                
            qr_x, qr_y, qr_w, qr_h = d.rect
            
            # Check if we're using an upscaled image - need to scale coordinates back
            rot_h, rot_w = rot.shape[:2]
            scale_factor = 1.0
            if rot_h > h * 1.5 or rot_w > w * 1.5:
                # This is an upscaled version
                scale_factor = h / rot_h  # Assuming roughly square scaling
            
            # Extract QR code data
            try:
                qr_code_data = d.data.decode("utf-8")
                if not qr_code_data or len(qr_code_data.strip()) == 0:
                    continue
            except (UnicodeDecodeError, AttributeError) as e:
                # Handle malformed UTF-8 or missing data
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"QR decode error: {e}")
                continue
            
            # Calculate center of QR code in rotated image coordinates (scaled)
            qr_center_x_rot = (qr_x + qr_w // 2) * scale_factor
            qr_center_y_rot = (qr_y + qr_h // 2) * scale_factor
            
            # Map back to original image coordinates
            orig_h, orig_w = h, w
            if angle == 0:
                center_x = qr_center_x_rot
                center_y = qr_center_y_rot
            elif angle == 90:
                # 90° clockwise rotation: (x, y) in rotated -> (h - y, x) in original
                center_x = orig_h - qr_center_y_rot
                center_y = qr_center_x_rot
            elif angle == 180:
                # 180° rotation: (x, y) in rotated -> (w - x, h - y) in original
                center_x = orig_w - qr_center_x_rot
                center_y = orig_h - qr_center_y_rot
            else:  # 270
                # 270° clockwise (90° counter-clockwise): (x, y) in rotated -> (y, w - x) in original
                center_x = qr_center_y_rot
                center_y = orig_w - qr_center_x_rot
            
            # Determine position based on center location relative to image boundaries
            is_left = center_x < orig_w / 2
            is_top = center_y < orig_h / 2
            
            # Determine position string
            if is_top and is_left:
                position = "top_left"
            elif is_top and not is_left:
                position = "top_right"
            elif not is_top and is_left:
                position = "bottom_left"
            else:
                position = "bottom_right"
            
            # Return position, data, and coordinates
            return (position, qr_code_data, (int(center_x), int(center_y)))
    
    return None


def get_qr_code_info(bgr_region) -> Optional[str]:
    """
    Retrieve the decoded information from a QR code or Data Matrix code in a note region.
    Uses OpenCV QRCodeDetector as primary method for QR codes, pylibdmtx for Data Matrix codes,
    falls back to pyzbar for QR codes.
    
    This is a convenience function for agents to retrieve code information
    without needing position or coordinate data.
    
    Args:
        bgr_region: Cropped BGR image of a single note region
        
    Returns:
        Decoded QR code or Data Matrix code data as a UTF-8 string, or None if no code found or decoding failed
    """
    # Reuse detect_qr_in_region() to avoid code duplication
    result = detect_qr_in_region(bgr_region)
    if result:
        # Extract just the data from the tuple (position, code_data, (center_x, center_y))
        _, code_data, _ = result
        return code_data
    return None


__all__ = ["detect_qr_positions", "detect_qr_in_region", "get_qr_code_info"]
