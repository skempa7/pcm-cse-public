"""Execute the opt-in camera controller against Babylon's real camera math.

This checks event ownership, bounded movement, and pose reframing. It does not
substitute for browser scroll/zoom and visual collision inspection.
"""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = os.environ.get('PCM_NODE_BINARY') or shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')

@unittest.skipUnless(os.path.exists(NODE), 'Node unavailable')
class CameraNavigation(unittest.TestCase):
    def test_native_inputs_opt_in_drag_and_pose_bounds(self):
        script = ROOT/'web/patient3d/tests/camera-navigation.mjs'
        result=subprocess.run([NODE,str(script)],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_production_input_and_ui_contract(self):
        room=(ROOT/'web/patient3d/src/room.js').read_text()
        css=(ROOT/'web/patient3d/room.css').read_text()
        html=(ROOT/'web/patient3d/index.html').read_text()
        self.assertIn('camera.inputs.clear()',room)
        self.assertNotIn('attachControl(',room)
        self.assertIn('scene.preventDefaultOnPointerDown=false',room)
        self.assertIn('scene.preventDefaultOnPointerUp=false',room)
        self.assertNotIn('touch-action:none',css)
        self.assertIn('touch-action:auto',css)
        for label in ['Face','Upper body','Full patient','Reset view','Adjust view','Done adjusting','Zoom in','Zoom out']:
            self.assertIn('>'+label+'<',html)
        self.assertIn("navigation?.adjusting||lesson",room)
        for direction in ('left','right','up','down'):
            self.assertNotIn('data-camera="'+direction+'"',html)
        self.assertIn('Drag to orbit · Zoom with buttons',html)
        self.assertIn('constraints:orbitClearances',room)
        self.assertIn('mesh.refreshBoundingInfo(true,true)',room)

if __name__=='__main__':unittest.main()
