import os
import Image
import printerConfig

h_size = 612
v_size = 816
v_offset = 0

def background_img():
    overlay_path = os.path.join(printerConfig.DATA_DIR, "overlay.png")
    return Image.open(overlay_path)

def add_overlay(src_path, dest_path):
    '''
    adds an overlay to image at src_path and deposits the result at dest_path
    '''
    bg = background_img()
    fg = Image.open(src_path)

    bg.paste(fg, (0,v_offset))
    bg.save(dest_path)

