"""Apply the unexecuted attachment probe only to a disposable exact-head checkout."""
import argparse,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('checkout');a=p.parse_args();r=pathlib.Path(a.checkout)
sha=subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip()
assert sha=='a0bca744067d04f05904319d3d919be30c336556','requires pinned candidate'
f=r/'libs/cua-driver/rust/crates/cua-driver-core/src/browser/store.rs';s=f.read_text()
assert 'experimental_stitched_metadata_retires' not in s,'already applied'
assert s.rstrip().endswith('}')
probe=pathlib.Path(__file__).with_name('stitched_object_probe.rs.inc').read_text()
f.write_text(s.rstrip()[:-1]+probe+'\n}\n')
print('Applied test-only prototype. Not compiled or executed by this command.')
