"""Synthetic sRGB ICC display checks; preview transformations never touch files."""
import hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageCms,ImageOps
import color_preview_v1 as preview


class ColorPreviewContracts(unittest.TestCase):
    def test_untagged_preview_matches_old_orientation_and_thumbnail(self):
        for orientation in range(1,9):
            image=Image.fromarray(np.arange(30*40*3,dtype=np.uint8).reshape(30,40,3));image.getexif()[274]=orientation
            expected=ImageOps.exif_transpose(image);expected.thumbnail((900,550));before=image.tobytes()
            actual=preview.display_preview(image);np.testing.assert_array_equal(np.asarray(actual),np.asarray(expected))
            self.assertEqual(image.tobytes(),before);self.assertEqual(image.getexif()[274],orientation)

    def test_ICC_conversion_runs_only_after_bounded_thumbnail_and_input_is_unchanged(self):
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        image=Image.new('RGB',(2000,1400),(130,120,110));image.info['icc_profile']=profile;before=image.tobytes();info=dict(image.info)
        real=preview.ImageCms.profileToProfile;sizes=[]
        def convert(actual,*args,**kwargs):
            sizes.append(actual.size);self.assertLessEqual(actual.width,900);self.assertLessEqual(actual.height,550)
            self.assertFalse(kwargs['inPlace']);return real(actual,*args,**kwargs)
        with patch.object(preview.ImageCms,'profileToProfile',side_effect=convert):result=preview.display_preview(image)
        self.assertEqual(len(sizes),1);self.assertLessEqual(result.width,900);self.assertLessEqual(result.height,550)
        self.assertEqual(image.tobytes(),before);self.assertEqual(image.info,info)

    def test_profile_conversion_does_not_rewrite_the_final_png(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'final.png';profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
            Image.new('RGB',(50,40),(120,130,140)).save(path,icc_profile=profile);before=path.read_bytes()
            with Image.open(path)as image:preview.display_preview(image)
            self.assertEqual(path.read_bytes(),before)

    def test_invalid_profile_is_explicit_failure_not_fake_color_conversion(self):
        image=Image.new('RGB',(40,30));image.info['icc_profile']=b'not a valid ICC'
        with self.assertRaisesRegex(ValueError,'display_preview_RGB_ICC_not_supported'):preview.display_preview(image)

    def test_GUI_save_copies_final_ICC_file_byte_for_byte(self):
        import tkinter as tk
        import unified_gui
        try:root=tk.Tk()
        except tk.TclError as error:self.skipTest('Display unavailable: '+str(error))
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory()as directory:
                directory=Path(directory);final=directory/'final.png';destination=directory/'saved.png';original=directory/'original.png'
                profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
                Image.new('RGB',(50,40),(120,130,140)).save(final,icc_profile=profile);original.write_bytes(b'unchanged original')
                app=unified_gui.App(root);root.update_idletasks();app.source=str(original);app.output=str(final);app._output_generation=app._generation
                with patch.object(unified_gui.filedialog,'asksaveasfilename',return_value=str(destination)):app.save()
                self.assertEqual(destination.read_bytes(),final.read_bytes());self.assertEqual(original.read_bytes(),b'unchanged original')
                with Image.open(destination)as image:self.assertEqual(image.info['icc_profile'],profile)
        finally:root.update_idletasks();root.destroy()


if __name__=='__main__':unittest.main()
