import asyncio,cProfile,pstats,pathlib
from run_p0_trials import trial,fixture,ROOT
with fixture() as url:
 p=cProfile.Profile();p.enable();asyncio.run(trial(url,'guarded',900));p.disable();p.dump_stats(ROOT/'guarded-loop.prof')
 with (ROOT/'guarded-loop-profile.txt').open('w') as f:pstats.Stats(p,stream=f).strip_dirs().sort_stats('cumulative').print_stats(35)
