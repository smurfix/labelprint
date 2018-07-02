#!/usr/bin/python3

from __future__ import print_function, division, with_statement
"""
This program prints labels with barcodes.

The idea is that a text file containing
12345
foo
bar baz whatever

is converted to two lines with maximal font size (i.e. line wrapping
disabled) plus a barcode (whatever codec works best) with embedded text.

Based off python example print_editor that comes with pygtk source:
Alexander Larsson (C version)
Gustavo Carneiro (Python translation)
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Pango, GObject, Gdk, Gio, PangoCairo, GLib, GdkPixbuf
Gdk.threads_init()

import sys
import math
import cairo
import PIL
import PIL.ImageOps
import PIL.ImageChops
import barcode as pybars
import io
from barcode.writer import ImageWriter
if ImageWriter is None:
    raise RuntimeError("You need to install PIL")
SCALE = float(Pango.SCALE)
RES_I = 72
RES = RES_I/2.54 # dots per mm
INIT_FONTSIZE=200

SETTINGS = (
('cover-after', 'none'),
('print-at', 'now'),
('scale', '100'),
('reverse', 'false'),
('print-pages', 'all'),
('print-at-time', ''),
('cups-PrintQuality', 'Fast'),
('cups-RollFedMedia', 'Roll'),
('cups-job-sheets', 'none,none'),
('cups-SoftwareMirror', 'False'),
('cups-ConcatPages', 'False'),
('cups-LabelPreamble', 'True'),
('cups-Align', 'Right'),
('cups-job-priority', '50'),
('cups-AdvanceDistance', '1Small'),
('collate', 'false'),
('cups-PrintDensity', '0PrinterDefault'),
('cups-CutMedia', 'LabelEnd'),
('cups-BytesPerLine', '90'),
('cups-NegativePrint', 'False'),
('cups-MirrorPrint', 'False'),
('n-copies', '1'),
('cover-before', 'none'),
('number-up', '1'),
('page-set', 'all'),
('cups-number-up', '1'),
('printer', 'QL-560'),
)

# https://stackoverflow.com/questions/7610159/convert-pil-image-to-cairo-imagesurface
def pil2cairo(im):
    """Transform a PIL Image into a Cairo ImageSurface."""

    import sys
    import array
    assert sys.byteorder == 'little', 'We don\'t support big endian'
    if im.mode != 'RGBA':
        im = im.convert('RGBA')

    s = im.tobytes('raw', 'BGRA')
    a = array.array('B', s)
    dest = cairo.ImageSurface(cairo.FORMAT_ARGB32, im.size[0], im.size[1])
    ctx = cairo.Context(dest)
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    non_premult_src_wo_alpha = cairo.ImageSurface.create_for_data(
        a, cairo.FORMAT_RGB24, im.size[0], im.size[1])
    non_premult_src_alpha = cairo.ImageSurface.create_for_data(
        a, cairo.FORMAT_ARGB32, im.size[0], im.size[1])
    ctx.set_source_surface(non_premult_src_wo_alpha)
    ctx.mask_surface(non_premult_src_alpha)
    return dest

print_text = None
print_barcode = ""
if len(sys.argv) > 1:
    print_text = []
    with open(sys.argv[1], "r") as f:
        print_barcode = f.readline().strip()
        for x in f.readlines():
            print_text.append(x.strip())

def get_code(s):
    if any(1 for x in s if ord(x) > 127 or ord(x) < 32):
        raise RuntimeError("cannot emit " + repr(s))
## Code128 is more efficient than the others
#   if s.isdigit():
#       return "ITF"
#   elif s == s.upper():
#       return "Code39"
#   else:
    return "Code128"

class LabelPrinter:    
    PAGE_WIDTH=38
    LEFT_MARGIN=1
    RIGHT_MARGIN=1
    TOP_MARGIN=2
    BOTTOM_MARGIN=1

    selected_printer = None
    print_settings = None

    barcode = ""
    text = ""
    _need_reflow = False
    height = 999
    content = None # RecordingSurface
    font_size = 0

    def __init__(self):
        self.set_width(38.0)

    @property
    def BAR_H(self):
        return self.PAGE_WIDTH/5

    def set_width(self,width):
        self.PAGE_WIDTH = width
        self.setup_page()
        self._need_reflow = True

    @property
    def width_px(self):
        return int(RES * (self.PAGE_WIDTH-self.LEFT_MARGIN-self.RIGHT_MARGIN) + 0.9999)

    @property
    def height_px(self):
        return int(RES * self.height + 0.9999)

    def set_barcode(self, barcode):
        self.barcode = barcode
        self._need_reflow = True

    def set_text(self, text):
        self.text = text
        self._need_reflow = True

    def get_page_setup(self):
        paper = Gtk.PaperSize.new_custom("Endless","Endless", self.PAGE_WIDTH, self.height+self.TOP_MARGIN+self.BOTTOM_MARGIN, Gtk.Unit.MM)
        setup = Gtk.PageSetup()
        setup.set_paper_size(paper)
        setup.set_bottom_margin(self.BOTTOM_MARGIN, Gtk.Unit.MM)
        setup.set_left_margin(self.LEFT_MARGIN, Gtk.Unit.MM)
        setup.set_right_margin(self.RIGHT_MARGIN, Gtk.Unit.MM)
        setup.set_top_margin(self.TOP_MARGIN, Gtk.Unit.MM)
        return setup

    def setup_page(self, force=False):
        setup = self.get_page_setup()
        if force or self.selected_printer is None:
            settings = Gtk.PrintSettings()
            for a,b in SETTINGS:
                settings.set(a,b)
            settings.set_printer("QL-560")
            # show print dialog
            op = Gtk.PrintOperation()
            op.set_unit(Gtk.Unit.MM)

            def do_begin(op, context):
                self.print_settings = op.get_property("print-settings")
                self.selected_printer = self.print_settings.get_printer()
                op.cancel()
            op.connect("begin_print", do_begin)

            op.set_default_page_setup(setup)
            op.set_print_settings(settings)
            res = op.run(Gtk.PrintOperationAction.PRINT_DIALOG if force else Gtk.PrintOperationAction.PRINT)

            if res != Gtk.PrintOperationResult.CANCEL or self.selected_printer is None:
                raise RuntimeError("You need to click 'Print'.")

        # PrintOperation
    def reflow(self):
        if not self._need_reflow:
            return False

        self.content = cairo.RecordingSurface(cairo.Content.COLOR,None)
        self.content.set_fallback_resolution(RES_I,RES_I)
        ctx = cairo.Context(self.content)
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        self.gen_page(ctx)
        return True

    def gen_page(self, ctx):
        if self.barcode:
            bars = pybars.get(get_code(self.barcode), self.barcode, writer=ImageWriter())
            bars = bars.render(writer_options=dict(format="PNG", write_text=False))
            if bars.width > self.width_px:
                bars = None
            else:
                bars = pil2cairo(bars)
        else:
            bars = None

        # start with a white background
        # otherwise things get interesting
        ctx.set_source_rgb(1, 1, 1)
        ctx.rectangle(0,0, self.width_px,999*RES)
        ctx.fill()
        
        def make_text_layout(text, fontsize):
            layout = PangoCairo.create_layout(ctx)
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_font_description(Pango.FontDescription("Sans %d" % fontsize))
            #layout.set_width(int(width*Pango.SCALE))
            layout.set_width(-1)
            layout.set_text(text,-1)
            return layout

        if self.text:
            layout = make_text_layout(self.text, INIT_FONTSIZE)
            w,h = layout.get_pixel_size()
            fs = int(INIT_FONTSIZE * self.width_px / w * 0.95)
            layout = make_text_layout(self.text, fs)
            self.font_size = fs
            w,h = layout.get_pixel_size()
            ctx.move_to(self.width_px/2 - w/2, 0)
            ctx.set_source_rgb(0, 0, 0)
            PangoCairo.show_layout(ctx, layout)

            if False:
                ctx.save()
                ctx.set_source_rgb(255, 0, 0)
                ctx.rectangle(self.width_px/2 - w/2, self.TOP_MARGIN*RES, w, h)
                ctx.set_line_width(2)
                ctx.stroke()
                ctx.restore()

            h /= RES # mm
        else:
            h = 0
            self.font_size = 0
            fs = 2*INIT_FONTSIZE

        if bars is not None:
            s = int(self.width_px / bars.get_width())
            bw = bars.get_width() * s

            ctx.save()
            ctx.scale(s,s)
            ctx.set_source_surface(bars, (RES*self.PAGE_WIDTH/2 - bw/2)/s, h*RES/s)
            ctx.set_antialias(cairo.ANTIALIAS_NONE)
            ctx.paint()
            ctx.restore()

            if False:
                ctx.save()
                ctx.set_source_rgb(255, 0, 0)
                ctx.rectangle(int((self.width_px/2 - bw/2)), int(h*RES), int(bw), int(RES*self.BAR_H))
                ctx.stroke()
                ctx.restore()

            h += self.BAR_H

            # add text to the label.
            # The text is at most as large as the main text,
            # may cover 1/3rd of the barcode height,
            # and must be somewhat narrower than the barcode
            bfs = fs
            layout = make_text_layout(self.barcode, bfs)
            lw,lh = layout.get_pixel_size()
            sfh = RES*self.BAR_H/3/lh
            sfw = bw/1.2/lw
            sf = min(sfw,sfh)
            if sf < 1:
                bfs *= sf
                layout = make_text_layout(self.barcode, bfs)
                lw,lh = layout.get_pixel_size()

            ctx.set_source_rgb(1, 1, 1)
            ctx.rectangle(self.width_px/2 - lw/2 - lh/6, h*RES-lh, lw+lh/3, lh+1)
            ctx.fill()

            ctx.set_source_rgb(0, 0, 0)
            ctx.move_to(self.width_px/2 - lw/2, h*RES-lh)
            PangoCairo.show_layout(ctx, layout)

        self.height = h+self.TOP_MARGIN+self.BOTTOM_MARGIN

    def print(self, preview=False):
        self.setup_page()

        setup = self.get_page_setup()
        op = Gtk.PrintOperation()
        op.set_default_page_setup(setup)

        op.set_print_settings(self.print_settings)
        #op.set_default_page_setup(self.page_setup)
        op.set_unit(Gtk.Unit.MM)
        op.connect("begin_print", self.begin_print)
        op.connect("draw_page", self.draw_page)

        res = op.run(Gtk.PrintOperationAction.PREVIEW if preview else Gtk.PrintOperationAction.PRINT_DIALOG)
    
    def scan_print(self, operation, context):
        width = context.get_width()
        size_hint = INIT_FONTSIZE
        _, size_hint = self.compute_heigth_fontsize(width, size_hint)
        self.height, self.font_size = self.compute_heigth_fontsize(width, size_hint)

    def begin_print(self, operation, context):
        operation.set_n_pages(1) # len(page_breaks) + 1)

    def draw_nothing (self, operation, context, page_number):
        pass

    def draw_page (self, operation, context, page_number):
        #self.draw_image(context.get_cairo_context())
        self.draw_direct_image(context.get_cairo_context())

    def draw_direct_image(self, ctx):
        #ctx.translate(self.LEFT_MARGIN,self.TOP_MARGIN)
        p = 1/RES
        ctx.scale(p,p)
        self.gen_page(ctx)

    def draw_image(self, ctx):
        #ctx.rectangle(self.LEFT_MARGIN,self.TOP_MARGIN,self.PAGE_WIDTH-self.LEFT_MARGIN-self.RIGHT_MARGIN,self.height-self.TOP_MARGIN-self.BOTTOM_MARGIN)
        ctx.rectangle(0, 0, self.PAGE_WIDTH,self.height)
        p = 1/RES
        ctx.scale(p,p)
        ctx.set_source_surface(self.content, self.LEFT_MARGIN/p, self.TOP_MARGIN/p)
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        ctx.fill()

APPNAME="labelprint"
APPVERSION="0.1"

class LabelUI(object):
    prn = None
    _reflow_timer = None
    
    def __init__(self):
        #gnome.init(APPNAME, APPVERSION)
        self.prn = LabelPrinter()

        self.widgets = Gtk.Builder()
        self.widgets.add_from_file(APPNAME+".glade")

        d = {}
        for k in dir(self):
            if not k.startswith("on_"):
                continue
            v = getattr(self,k)
            if not callable(v):
                continue
            d[k] = v
        self.widgets.connect_signals(d)

    def init_done(self):
        self['main'].show_all()

    def __getitem__(self,name):
        return self.widgets.get_object(name)

    # support

    def _will_reflow(self):
        self._no_reflow()
        self._reflow_timer = GObject.timeout_add(500, self._run_reflow)

    def _no_reflow(self):
        if self._reflow_timer is None:
            return
        GObject.source_remove(self._reflow_timer)
        self._reflow_timer = None
        
    def _run_reflow(self):
        self._reflow_timer = None
        self.reflow()

    def reflow(self):
        self._no_reflow()

        if not self.prn.reflow(): # nothing to do
            return

        preview = self['img_label']
        if preview is not None:
            preview.queue_draw()

        self['txt_length'].set_text("%.1f mm" % (self.prn.height,))
        self['txt_fontsize'].set_text("%.1f pt" % (self.prn.font_size,))

    def _set_prn(self):
        txt = self['txt_code']
        txt = txt.get_text()
        self.prn.set_barcode(txt)

        buf = self['label_buf']
        txt = buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        self.prn.set_text(txt)

        pwg = self['pw_38']
        for btn in pwg.get_group():
            if not btn.get_active():
                continue
            w = float(Gtk.Buildable.get_name(btn)[3:])  # pw_###
            self.prn.set_width(w)
            break

        self.reflow()
        
    # events

    def on_draw_label(self, wid, ctx):
        if not self.prn or not self.prn.content:
            return
        ctx.save()
        ctx.set_source_rgb(1,1,1)
        ctx.paint()
        w = self.prn.width_px
        h = self.prn.height_px
        #s = ctx.get_target()
        #wp = s.get_width()
        #hp = s.get_height()
        s = wid
        wp = wid.get_allocated_width()
        hp = wid.get_allocated_height()
        p = min(wp/w, hp/h)
        if p < 0.01:
            # Sometimes draw() is called with a null surface
            return
        ctx.scale(p,p)
        ctx.set_source_surface(self.prn.content, 0, 0)
        ctx.rectangle(*self.prn.content.ink_extents())
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        ctx.paint()
        ctx.restore()

    def on_barcode_changed(self, field):
        self.prn.set_barcode(field.get_text())
        self._will_reflow()

    def on_pw_toggled(self, btn):
        if not btn.get_active():
            return
        w = float(Gtk.Buildable.get_name(btn)[3:])  # pw_###
        self.prn.set_width(w)
        self._will_reflow()

    def on_text_changed(self, buf):
        txt = buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        self.prn.set_text(txt)
        self._will_reflow()

    def on_setup_clicked(self,*foo):
        self.prn.setup_page(True)
        self.reflow()

    def on_p_press(self,btn,ev):
        st = ev.get_state()
        self.did_shift = bool(st & st.SHIFT_MASK)

    def on_p_release(self,*foo):
        pass

    def on_print_clicked(self,*foo):
        self.prn.print(preview=self.did_shift)
        self.reflow()

    def on_main_destroy(self,window):
        # main window goes away
        Gtk.main_quit()

    def on_main_delete_event(self,window,event):
        # True if the window should not be deleted
        return False

    def on_quit_clicked(self,x):
        Gtk.main_quit()

if __name__ == '__main__':
    ui = LabelUI()
    ui.init_done()

    Gtk.main()

