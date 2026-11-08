"""Exercise the actual workflow version guard without publishing anything."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT=next(parent for parent in Path(__file__).resolve().parents if (parent/'.github/workflows/release-on-main.yml').exists())
WORKFLOW=(ROOT/'.github/workflows/release-on-main.yml').read_text()
BODY=textwrap.dedent(WORKFLOW.split("python3 <<'PY'\n",1)[1].split('\n          PY',1)[0])

class ReleasePolicyTests(unittest.TestCase):
    def guard(self,version,kind,confirmation=None,ref='refs/heads/main'):
        with tempfile.TemporaryDirectory() as folder:
            output=str(Path(folder)/'output')
            env={'GITHUB_OUTPUT':output,'RELEASE_KIND':kind,'VERSION_CONFIRMATION':version if confirmation is None else confirmation,'RELEASE_REF':ref}
            with patch.dict(os.environ,env),patch.object(Path,'read_text',return_value=json.dumps({'version':version})),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                try:exec(compile(BODY,'workflow-version-guard','exec'),{'__name__':'__main__'})
                except SystemExit:return False
            return Path(output).is_file()
    def test_workflow_is_manual_and_defaults_to_prerelease(self):
        trigger=WORKFLOW.split('on:\n',1)[1].split('\npermissions:',1)[0]
        self.assertIn('workflow_dispatch:',trigger);self.assertNotIn('push:',trigger);self.assertNotIn('pull_request:',trigger)
        self.assertIn('default: prerelease',trigger)
        self.assertIn("prerelease: ${{ inputs.release_kind != 'stable' }}",WORKFLOW)
        self.assertIn("make_latest: ${{ inputs.release_kind == 'stable' && 'true' || 'false' }}",WORKFLOW)
    def test_confirmed_developer_branch_prerelease_is_allowed(self):
        self.assertTrue(self.guard('1.2.3-dev.1','prerelease',ref='refs/heads/development'))
    def test_developer_version_cannot_be_stable(self):
        self.assertFalse(self.guard('1.2.3-dev.1','stable'))
    def test_stable_requires_main_and_exact_confirmation(self):
        self.assertFalse(self.guard('1.2.3','stable',ref='refs/heads/development'))
        self.assertFalse(self.guard('1.2.3','stable',confirmation='wrong'))
        self.assertTrue(self.guard('1.2.3','stable'))
    def test_stable_number_is_not_a_developer_release(self):
        self.assertFalse(self.guard('1.2.3','prerelease'))
    def test_missing_or_invalid_release_kind_is_rejected(self):
        self.assertFalse(self.guard('1.2.3-dev.1',''))
        self.assertFalse(self.guard('1.2.3-dev.1','other'))
