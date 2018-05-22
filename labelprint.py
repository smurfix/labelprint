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

#import gtkunixprint
import sys
import math
import cairo
#import gnome.ui
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
('cups-LabelPreamble', 'False'),
('cups-Align', 'Right'),
('cups-job-priority', '50'),
('cups-AdvanceDistance', '0None'),
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
    if s.isdigit():
        return "ITF"
    elif any(1 for x in s if ord(x) > 127 or ord(x) < 32):
        raise RuntimeError("cannot emit " + repr(s))
    elif s == s.upper():
        return "Code39"
    else:
        return "Code128"

class LabelPrinter:    
    PAGE_WIDTH=38
    SIDE_MARGIN=1
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
        return int(RES * self.PAGE_WIDTH + 0.9999)

    @property
    def height_px(self):
        return int(RES * self.height + 0.9999)

    def set_barcode(self, barcode):
        self.barcode = barcode
        self._need_reflow = True

    def set_text(self, text):
        self.text = text
        self._need_reflow = True

    def setup(self):
        # display printer setup dialog
    
        # , action=None, data=None, barcode=None, filename=None):
        self.layout = None
        self.font_size=12
        if action==None:
            # By default set the print action to preview
            action = Gtk.PRINT_OPERATION_ACTION_PREVIEW
        
        # Paper Size 
        #paper_size = Gtk.PaperSize(Gtk.PAPER_NAME_A4)


    def setup_page(self):
        paper = Gtk.PaperSize.new_custom("Endless","Endless",self.PAGE_WIDTH,self.height,Gtk.Unit.MM)
        setup = Gtk.PageSetup()
        setup.set_paper_size(paper)
        setup.set_bottom_margin(0, Gtk.Unit.MM)
        setup.set_left_margin(self.SIDE_MARGIN, Gtk.Unit.MM)
        setup.set_right_margin(self.SIDE_MARGIN, Gtk.Unit.MM)
        setup.set_top_margin(self.TOP_MARGIN, Gtk.Unit.MM)

        if self.selected_printer is None:
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

            op.set_print_settings(settings)
            res = op.run(Gtk.PrintOperationAction.PRINT_DIALOG)

            if res != Gtk.PrintOperationResult.CANCEL or self.selected_printer is None:
                raise RuntimeError("You need to click 'Print'.")

        # PrintOperation
    def reflow(self):
        if not self._need_reflow:
            return False
        if self.barcode:
            bars = pybars.get(get_code(self.barcode), self.barcode, writer=ImageWriter())
            bars = bars.render(writer_options=dict(format="PNG", write_text=False))
            if bars.width > self.width_px:
                bars = None
            else:
                bars = pil2cairo(bars)
        else:
            bars = None

        self.content = cairo.RecordingSurface(cairo.Content.COLOR,None)
        self.content.set_fallback_resolution(RES_I,RES_I)
        ctx = cairo.Context(self.content)
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
#        ctx.set_source_rgb(1,1,1)
#        ctx.paint()

        if self.text:
            def make_text_layout(fontsize):
                layout = PangoCairo.create_layout(ctx)
                layout.set_alignment(Pango.Alignment.CENTER)
                layout.set_font_description(Pango.FontDescription("Sans %d" % fontsize))
                #layout.set_width(int(width*Pango.SCALE))
                layout.set_width(-1)
                layout.set_text(self.text,-1)
                return layout
            layout = make_text_layout(INIT_FONTSIZE)
            w,h = layout.get_pixel_size()
            fs = int(INIT_FONTSIZE * self.width_px / w * 0.99)
            print("FONT",fs)
            layout = make_text_layout(fs)
            self.font_size = fs
            w,h = layout.get_pixel_size()
            print("WHn",w,h, self.width_px)
            ctx.move_to(self.width_px/2 - w/2, 0)
            ctx.set_source_rgb(0, 0, 0)
            PangoCairo.show_layout(ctx, layout)
            h /= RES # mm
        else:
            h = 0
            self.font_size = 0

        if bars is not None:
            s = int(self.width_px / bars.get_width())
            bw = bars.get_width() * s

            ctx.save()
            ctx.scale(s,s)
            ctx.set_source_surface(bars, (RES*self.PAGE_WIDTH/2 - bw/2)/s, h*RES/s)
            ctx.set_antialias(cairo.ANTIALIAS_NONE)
            ctx.paint()
            ctx.restore()
            h += self.BAR_H
        self.height = h
        return True


    def print(self):
        self.reflow()
        paper_size = Gtk.PaperSize.new_custom("Endless","Endless",self.PAGE_WIDTH,self.height+self.TOP_MARGIN+self.BOTTOM_MARGIN,Gtk.Unit.MM)
        self.page_setup.set_paper_size(paper_size)
        op = Gtk.PrintOperation()
        op.set_default_page_setup(self.page_setup)
        op.set_unit(Gtk.Unit.MM)
        op.connect("begin_print", self.begin_print)
        op.connect("draw_page", self.draw_page)

        if action == Gtk.PRINT_OPERATION_ACTION_EXPORT:
            op.set_export_filename(filename)
        res = op.run(action)
    
    def scan_print(self, operation, context):
        width = context.get_width()
        size_hint = INIT_FONTSIZE
        _, size_hint = self.compute_heigth_fontsize(width, size_hint)
        self.height, self.font_size = self.compute_heigth_fontsize(width, size_hint)

    def compute_height_fontsize(self, width, fontsize_hint=INIT_FONTSIZE):
        
        s = cairo.whatever()
        height = context.get_height()
        print(width)
        page_height = 0
        max_width = 0
        num_lines = len(self.text)
        print("num_lines: ", num_lines)

        for line in xrange(num_lines):
            self.layout = context.create_pango_layout()
            self.layout.set_alignment(Pango.ALIGN_LEFT)
            self.layout.set_font_description(Pango.FontDescription("Sans %d" % INIT_FONTSIZE))
            #self.layout.set_width(int(width*Pango.SCALE))
            self.layout.set_width(-1)
            self.layout.set_text(self.text[line])

            layout_line = self.layout.get_line(0)
            ink_rect, logical_rect = layout_line.get_extents()
            x_bearing, y_bearing, lwidth, lheight = logical_rect
            if max_width < lwidth/SCALE:
                max_width = lwidth/SCALE

            line_height = lheight / SCALE
            page_height += line_height
            print(ink_rect, logical_rect, page_height)

        print("Pre",page_height,self.font_size,max_width)
        usable = self.PAGE_WIDTH-2*self.SIDE_MARGIN
        page_height = page_height*usable/max_width
        self.font_size = INIT_FONTSIZE*usable/max_width

        self.height = page_height
        if self.bars is not None:
            self.height += self.BAR_H
        print("Post",self.height,self.font_size)
        #self.page_breaks = page_breaks

    def begin_print(self, operation, context):
        operation.set_n_pages(1) # len(page_breaks) + 1)

    def draw_nothing (self, operation, context, page_number):
        pass

    def draw_page (self, operation, context, page_number):
        self.draw_image(context)

    def draw_image(self, context):
        layout = context.create_pango_layout()
        layout.set_alignment(Pango.ALIGN_CENTER)
        layout.set_font_description(Pango.FontDescription("Sans "+str(self.font_size)))
        #layout.set_width(int(width*Pango.SCALE))
        layout.set_width(-1)
        layout.set_text("\n".join(self.text))
        
        cr = context.get_cairo_context()
        cr.set_source_rgb(0, 0, 0)
        
        pr, lr = layout.get_extents()
        print(pr,lr)
        cr.move_to(0,0)
        cr.show_layout(layout)

##        for line in xrange(num_lines):
##            line = iter.get_line()
##            _, logical_rect = iter.get_line_extents()
##            x_bearing, y_bearing, lwidth, lheight = logical_rect
##            baseline = iter.get_baseline()
##            if i == 0:
##                start_pos = y_bearing / SCALE
##            print("at",logical_rect,baseline,start_pos,line)
##            cr.move_to(x_bearing / SCALE, baseline / SCALE - start_pos)
##            cr.show_layout_line(line)
##            i += 1

        if self.bars is not None:
            # get the image
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(self.bars))
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
            cr.set_source_pixbuf(pixbuf, 0, lr[3]/SCALE)
            s = context.get_width()/pixbuf.get_width()
            cr.scale(s,s)
            #self.svgwidget = Gtk.Image.new_from_pixbuf(pixbuf)
##            m = PIL.ImageOps.grayscale(self.bars)
##            m = PIL.ImageOps.invert(m)
##            b = self.bars.convert("RGBA")
##            b.putalpha(m)
##
##            # chop off the top (white-only) rows of the barcode
##            bg = PIL.Image.new(b.mode, b.size, b.getpixel((0, 0)))
##            diff = PIL.ImageChops.difference(b, bg)
##            dbox = diff.getbbox()
##            bbox = b.getbbox()
##            bbox = (bbox[0], dbox[1], bbox[2], dbox[3])
##            b = b.crop(bbox)
##
##            # copy the barcode onto the image.
##            # TODO: use the buffer instead of going through PNG.
##            s = io.BytesIO()
##            b.save(s,"PNG")
##            s.seek(0)
##            img = cairo.ImageSurface.create_from_png(s)
##            s = context.get_width()/img.get_width()
##            cr.scale(s,s)
##            cr.set_antialias(cairo.ANTIALIAS_NONE)
##            #cr.set_operator(cairo.OPERATOR_ADD)
##            cr.set_source_surface(img, 0, lr[3]/SCALE/s) # self.height-self.BAR_H)
##            cr.paint()
            
            # Print the barcode text. First, undo the scaling.
##            cr.scale(1/s,1/s)
            layout = context.create_pango_layout()
            layout.set_alignment(Pango.ALIGN_CENTER)
            layout.set_font_description(Pango.FontDescription("Sans "+str(self.font_size*0.7)))
            #layout.set_width(int(width*Pango.SCALE))
            layout.set_width(-1)
            layout.set_text(self.barcode)
            
            cr.set_source_rgb(0, 0, 0)
            
            npr, nlr = layout.get_extents()
            print(pr,lr,cr.get_matrix())
            tw = layout.get_extents()[1][2]/SCALE
            pw = cr.clip_extents()
            pw = pw[2]
            cr.translate(pw/2-tw/2,lr[3]/SCALE+self.BAR_H+(npr[1]-npr[3])/SCALE)
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(nlr[0]/SCALE-0.5, nlr[1]/SCALE-0.2, nlr[2]/SCALE+1, nlr[3]/SCALE+1)
            cr.fill()
            cr.set_source_rgb(0, 0, 0)
            cr.show_layout(layout)

def on_print_preview(widget=None):
    """
    Show the print preview.
    """
    global print_text,print_barcode
    global printer
    action = Gtk.PRINT_OPERATION_ACTION_PREVIEW
    printer = LabelPrinter(action, data=print_text, barcode=print_barcode)

def on_print_export(widget=None):
    """
    Export to a file. This requires the "export-filename" property to be set.
    """
    print("on_print_export")
    global print_text, print_barcode
    action = Gtk.PRINT_OPERATION_ACTION_EXPORT
    printer = LabelPrinter(action, data=print_text, barcode=print_barcode, filename="MyPDFDocument.pdf")

def on_print_dialog(widget=None):
    """
    Show the print dialog.
    """
    global print_text, print_barcode
    action = Gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG
    printer = LabelPrinter(action, data=print_text, barcode=print_barcode)

def on_print_immediately(widget=None):
    """
    Start printing immediately without showing the print dialog.
    Based on the current print settings.
    """
    global print_text, print_barcode
    action = Gtk.PRINT_OPERATION_ACTION_PRINT
    printer = LabelPrinter(action, data=print_text, barcode=print_barcode)

def on_file_selected(widget=None):
    global print_text, print_barcode
    data=[]
    with open(widget.get_filename(), "r") as f:
        print_barcode = f.readline().strip()
        for x in f.readlines():
            data.append(x.strip())
    print_text=data

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
        print("SC",p,w,h,wp,hp)
        print("R",*self.prn.content.ink_extents())
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
        print("setup",*foo)
        self.prn.setup()
        self.reflow()

    def on_main_destroy(self,window):
        # main window goes away
        Gtk.main_quit()

    def on_main_delete_event(self,window,event):
        # True if the window should not be deleted
        return False

    def on_quit_clicked(self,x):
        Gtk.main_quit()



def _old_main():
    """
    PyGTK GUI to test gnome printing technologies
    """
    global printer
    printer = LabelPrinter()

    data=None
    win = Gtk.Window()

    win.connect("delete_event", lambda w,e: Gtk.main_quit())
    
    vbox = Gtk.VBox(False, 0)
    hbox = Gtk.HBox(False, 0)
    
    button_open = Gtk.FileChooserButton("Open File")
    button_open.connect("selection-changed", on_file_selected)
    
    print_preview = Gtk.Button("Print Preview")
    print_preview.connect("clicked", on_print_preview)

    print_immediately = Gtk.Button("Print Immediately")
    print_immediately.connect("clicked", on_print_immediately)

    print_export = Gtk.Button("Export to PDF")
    print_export.connect("clicked", on_print_export)

    print_dialog = Gtk.Button("Print Dialog")
    print_dialog.connect("clicked", on_print_dialog)

    hbox.pack_start(print_dialog, True, True, 5)
    hbox.pack_start(print_immediately, True, True, 5)
    hbox.pack_start(print_export, True, True, 5)
    hbox.pack_start(print_preview, True, True, 5)
    vbox.pack_start(button_open, False, True, 5)
    vbox.pack_start(hbox, False, True, 5)

    win.add(vbox)
    win.show_all()

if __name__ == '__main__':
    ui = LabelUI()
    ui.init_done()

    Gtk.main()

