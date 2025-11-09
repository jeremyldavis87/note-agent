"""
Interactive preprocessing viewer UI using Streamlit.

This UI allows users to visualize preprocessing steps, adjust parameters,
and see detected regions with bounding boxes.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

try:
    from PIL import Image
except ImportError:
    Image = None


def load_image(image_path: str) -> Optional[np.ndarray]:
    """Load image from file path."""
    bgr = cv2.imread(str(image_path))
    return bgr


def bgr_to_rgb(bgr: np.ndarray) -> np.ndarray:
    """Convert BGR to RGB for display."""
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def draw_bounding_boxes(
    image: np.ndarray,
    regions: list,
    color: tuple = (255, 0, 0),
    thickness: int = 2
) -> np.ndarray:
    """Draw bounding boxes on image."""
    result = image.copy()
    for region in regions:
        x, y, w, h = region.bbox
        cv2.rectangle(result, (x, y), (x + w, y + h), color, thickness)
        # Add label if available
        if hasattr(region, 'position_label') and region.position_label:
            cv2.putText(
                result,
                region.position_label,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1
            )
    return result


def draw_qr_codes(
    image: np.ndarray,
    qr_metadata_list: list,
    color: tuple = (0, 255, 0),
    thickness: int = 2
) -> np.ndarray:
    """Draw QR code bounding boxes on image."""
    result = image.copy()
    for qr_meta in qr_metadata_list:
        # Handle both dict and object formats
        if isinstance(qr_meta, dict):
            x, y, w, h = qr_meta["position"]
            data = qr_meta["data"]
        else:
            x, y, w, h = qr_meta.position
            data = qr_meta.data
        
        cv2.rectangle(result, (x, y), (x + w, y + h), color, thickness)
        # Add label
        label = f"QR: {data[:20]}..." if len(data) > 20 else f"QR: {data}"
        cv2.putText(
            result,
            label,
            (x, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1
        )
    return result


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title="Note Agent - Preprocessing Viewer",
        page_icon="📝",
        layout="wide"
    )
    
    st.title("📝 Note Agent - Preprocessing Viewer")
    st.markdown("Interactive visualization of image preprocessing steps")
    
    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        
        # Image upload
        uploaded_file = st.file_uploader(
            "Upload an image",
            type=["jpg", "jpeg", "png", "bmp"]
        )
        
        image_path_input = st.text_input(
            "Or enter image path:",
            placeholder="/path/to/image.jpg"
        )
        
        # Preprocessing parameters
        st.header("Preprocessing Parameters")
        denoise_strength = st.slider(
            "Denoising Strength",
            min_value=1,
            max_value=20,
            value=10,
            help="Higher values = more denoising"
        )
        
        contrast_low = st.slider(
            "Contrast Low Percentile",
            min_value=0,
            max_value=10,
            value=2,
            help="Lower percentile for contrast stretching"
        )
        
        contrast_high = st.slider(
            "Contrast High Percentile",
            min_value=90,
            max_value=100,
            value=98,
            help="Upper percentile for contrast stretching"
        )
        
        # Visualization options
        st.header("Visualization Options")
        show_regions = st.checkbox("Show Detected Regions", value=True)
        show_qr_codes = st.checkbox("Show QR Codes", value=True)
        show_preprocessed = st.checkbox("Show Preprocessed Image", value=True)
    
    # Load image
    image = None
    if uploaded_file is not None:
        image_bytes = uploaded_file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_path_input:
        image_path = Path(image_path_input)
        if image_path.exists():
            image = load_image(str(image_path))
        else:
            st.error(f"Image not found: {image_path_input}")
    
    if image is None:
        st.info("Please upload an image or enter an image path to get started.")
        return
    
    # Display image info
    h, w = image.shape[:2]
    st.sidebar.info(f"Image size: {w}x{h} pixels")
    
    # Import processing functions (lazy import to avoid errors if not available)
    try:
        import sys
        from pathlib import Path
        # Add src directory to path for imports
        src_dir = Path(__file__).resolve().parent.parent
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        from image_ops.preprocess import preprocess_image
        from image_ops.qr import detect_qr_positions
        from detect.multinote import detect_regions
        from image_ops.color import dominant_color, describe_background_color
    except ImportError as e:
        st.error(f"Failed to import processing modules: {e}")
        import traceback
        st.code(traceback.format_exc())
        return
    
    # Process image
    with st.spinner("Processing image..."):
        # Original image
        original_rgb = bgr_to_rgb(image)
        
        # Preprocessing
        pre = preprocess_image(image)
        preprocessed_rgb = bgr_to_rgb(
            cv2.cvtColor(pre.image, cv2.COLOR_GRAY2BGR)
            if len(pre.image.shape) == 2
            else pre.image
        )
        
        # Color analysis
        dom_color = dominant_color(image)
        bg_label = describe_background_color(dom_color)
        
        # Region detection
        regions = detect_regions(image, force_single=False)
        
        # QR code detection
        qr_results = detect_qr_positions(image)
        # Convert to list of dicts for display
        qr_metadata_list = [{"data": data, "position": pos} for data, pos in qr_results]
    
    # Display results
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Original Image")
        
        # Original with overlays
        display_image = original_rgb.copy()
        if show_regions and regions:
            display_image = draw_bounding_boxes(display_image, regions)
        if show_qr_codes and qr_metadata_list:
            display_image = draw_qr_codes(display_image, qr_metadata_list)
        
        st.image(display_image, use_column_width="auto")
        
        # Image info
        st.info(f"**Background Color:** {bg_label}\n\n**Dominant RGB:** {dom_color}")
    
    with col2:
        st.subheader("Preprocessed Image" if show_preprocessed else "Original Image")
        
        if show_preprocessed:
            display_image_pre = preprocessed_rgb.copy()
            if show_regions and regions:
                display_image_pre = draw_bounding_boxes(display_image_pre, regions, color=(255, 165, 0))
            if show_qr_codes and qr_metadata_list:
                display_image_pre = draw_qr_codes(display_image_pre, qr_metadata_list, color=(0, 255, 255))
            st.image(display_image_pre, use_column_width="auto")
            
            # Preprocessing metrics
            metrics = pre.metrics
            st.info(
                f"**Contrast Range:** {metrics.get('contrast_range', 0):.1f}\n\n"
                f"**Dimensions:** {metrics.get('width', 0)}x{metrics.get('height', 0)}"
            )
        else:
            st.image(original_rgb, use_column_width="auto")
    
    # Detected regions table
    if regions:
        st.subheader(f"Detected Regions ({len(regions)})")
        region_data = []
        for idx, region in enumerate(regions):
            x, y, w, h = region.bbox
            region_data.append({
                "Index": idx + 1,
                "Position": region.position_label,
                "X": x,
                "Y": y,
                "Width": w,
                "Height": h,
                "Color": getattr(region, 'note_color', 'N/A')
            })
        st.dataframe(region_data, use_container_width=True)
    
    # QR codes table
    if qr_metadata_list:
        st.subheader(f"QR Codes Detected ({len(qr_metadata_list)})")
        qr_data = []
        for idx, qr_meta in enumerate(qr_metadata_list):
            x, y, w, h = qr_meta["position"]
            data = qr_meta["data"]
            qr_data.append({
                "Index": idx + 1,
                "Data": data[:50] + "..." if len(data) > 50 else data,
                "Position": f"({x}, {y})",
                "Size": f"{w}x{h}"
            })
        st.dataframe(qr_data, use_container_width=True)
    
    # Export options
    st.subheader("Export")
    col_export1, col_export2 = st.columns(2)
    
    with col_export1:
        if st.button("Export Preprocessed Image"):
            # Convert to PIL Image for download
            if Image:
                pil_image = Image.fromarray(preprocessed_rgb)
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                st.download_button(
                    "Download Preprocessed Image",
                    buf.getvalue(),
                    "preprocessed.png",
                    "image/png"
                )
    
    with col_export2:
        if st.button("Export with Overlays"):
            overlay_image = original_rgb.copy()
            if regions:
                overlay_image = draw_bounding_boxes(overlay_image, regions)
            if qr_metadata_list:
                overlay_image = draw_qr_codes(overlay_image, qr_metadata_list)
            
            if Image:
                pil_image = Image.fromarray(overlay_image)
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                st.download_button(
                    "Download Overlay Image",
                    buf.getvalue(),
                    "overlay.png",
                    "image/png"
                )


if __name__ == "__main__":
    main()

