"""Package source/configuration only: no local databases, secrets or signing keys."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
p=argparse.ArgumentParser();p.add_argument('--commit',required=True);args=p.parse_args()
assert len(args.commit)==40 and all(c in '0123456789abcdef' for c in args.commit)
root=Path(__file__).resolve().parents[1]
out=root/'dist/FG-Link-Panel-Standalone.zip';out.parent.mkdir(exist_ok=True)
files=['Dockerfile','requirements.txt','docker-compose.yml','docker-compose.panel.yml','Caddyfile','direct_mttl_lab.py','install-panel.sh','update-panel-bundle.sh','update-direct-users.sh']
with ZipFile(out,'w',ZIP_DEFLATED) as z:
 for name in files:z.write(root/'server'/name,'FG-Link-Panel/server/'+name)
 for path in sorted((root/'server/app').glob('*.py')):z.write(path,'FG-Link-Panel/server/app/'+path.name)
 z.writestr('FG-Link-Panel/server/BUNDLE_COMMIT',args.commit+'\n')
 z.writestr('FG-Link-Panel/install.sh','#!/bin/bash\nset -e\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nexec bash server/install-panel.sh\n')
 z.writestr('FG-Link-Panel/update-existing.sh','#!/bin/bash\nset -e\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nexec bash server/update-panel-bundle.sh\n')
 z.write(root/'docs/FG_LINK_PANEL_INSTALL_AR.md','FG-Link-Panel/README-AR.md')
print(out)
