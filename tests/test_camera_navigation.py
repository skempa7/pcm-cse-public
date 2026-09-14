"""Execute the deliberate-drag camera controller against Babylon's real camera math.

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
    def test_native_inputs_horizontal_touch_drag_and_pose_bounds(self):
        script = ROOT/'web/patient3d/tests/camera-navigation.mjs'
        result=subprocess.run([NODE,str(script)],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_production_input_and_ui_contract(self):
        room=(ROOT/'web/patient3d/src/room.js').read_text()
        css=(ROOT/'web/patient3d/room.css').read_text()
        html=(ROOT/'web/patient3d/index.html').read_text()
        self.assertIn('camera.inputs.clear()',room)
        self.assertIn('doNotHandleTouchAction:true',room)
        self.assertNotIn('attachControl(',room)
        self.assertIn('scene.preventDefaultOnPointerDown=false',room)
        self.assertIn('scene.preventDefaultOnPointerUp=false',room)
        self.assertNotIn('touch-action:none',css)
        self.assertIn('touch-action:pan-y pinch-zoom',css)
        # The camera controls are icon buttons now, so their name lives in
        # aria-label rather than in text content. Checking '>Face<' was really
        # checking the old markup; checking the accessible name is what the
        # requirement actually is. 'Adjust view' / 'Done adjusting' are gone
        # with the control they named -- drag replaced the adjust mode.
        for label in ['Face','Upper body','Full patient','Reset view','Zoom in','Zoom out']:
            self.assertIn('aria-label="'+label+'"',html,
                          label+' camera control has no accessible name')
        # 'Adjust view' / 'Done adjusting' proxied the room's own camera nav in
        # a second toolbar and were removed. Assert they stay gone.
        for removed in ['Adjust view','Done adjusting']:
            self.assertNotIn(removed,html,removed+' reappeared as a duplicate control')
        # The separate adjust-view mode is gone; orbiting is gated by the
        # encounter phase and suspended during a technique lesson instead.
        self.assertIn("lesson", room)
        self.assertIn("allowed:", room)
        for direction in ('left','right','up','down'):
            self.assertNotIn('data-camera="'+direction+'"',html)
        # The same guidance now lives on the canvas's accessible label.
        self.assertIn('Drag horizontally to rotate around the patient',html)
        self.assertIn('constraints:orbitClearances',room)
        self.assertIn('mesh.refreshBoundingInfo(true,true)',room)

if __name__=='__main__':unittest.main()
