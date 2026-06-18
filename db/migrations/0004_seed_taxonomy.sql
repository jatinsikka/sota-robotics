-- 0004_seed_taxonomy.sql
insert into domains (slug, name, description) values
 ('humanoid-vla-manip','Humanoid VLA & manipulation','VLA foundation models, dexterous & bimanual manipulation'),
 ('locomotion-wbc','Locomotion & whole-body control','Legged/bipedal locomotion, whole-body control'),
 ('world-models','World models','Learned world/video predictors used for control'),
 ('world-action-models','World-action models','Action-conditioned world prediction (WAM)'),
 ('sim2real-rl','Sim-to-real & RL for control','Domain randomization, real-world RL, sim2real transfer'),
 ('robot-perception','Robot perception','3D vision, grasping, 6-DoF pose estimation'),
 ('lfd-robot-data','Learning from demonstration & robot data','Imitation learning, teleop, cross-embodiment datasets'),
 ('navigation-vln','Navigation / VLN','Embodied & vision-language navigation')
on conflict (slug) do nothing;

insert into benchmarks (domain_id, slug, name, measures, metric, results_url, is_saturated, notes)
select d.id, v.slug, v.name, v.measures, v.metric, v.results_url, v.is_saturated, v.notes
from (values
 ('humanoid-vla-manip','libero','LIBERO','Lifelong language-conditioned tabletop manipulation','success_rate','https://libero-project.github.io', true,  'Saturated >97%; rank by robustness (LIBERO-Plus), not raw score'),
 ('humanoid-vla-manip','robocasa','RoboCasa','Large-scale household manipulation (GR-1 tabletop)','success_rate','https://robocasa.ai', false, 'Discriminating: SOTA ~50-57%'),
 ('humanoid-vla-manip','simplerenv','SimplerEnv','Real-to-sim manipulation reproduction','success_rate','https://github.com/simpler-env/SimplerEnv', false, 'Visual Matching / Variant Aggregation'),
 ('humanoid-vla-manip','maniskill3','ManiSkill3','GPU-parallel manipulation suite','success_rate','https://github.com/haosulab/ManiSkill', false, null),
 ('humanoid-vla-manip','roboarena','RoboArena','Cross-lab real-world pairwise policy ranking','elo','https://robo-arena.github.io', false, 'Real-world Elo; credible anti-gaming signal; runs through Dec 2026'),
 ('robot-perception','bop','BOP','6-DoF object pose estimation','average_recall','https://bop.felk.cvut.cz/leaderboards', false, 'Has a live online eval server/API (gold standard)'),
 ('locomotion-wbc','humanoidbench','HumanoidBench','Simulated humanoid whole-body loco+manip','success_rate','https://humanoid-bench.github.io', false, null),
 ('navigation-vln','habitat','Habitat / ObjectNav','Embodied navigation','spl','https://aihabitat.org', false, 'EvalAI-hosted challenge'),
 ('lfd-robot-data','open-x-embodiment','Open X-Embodiment','Cross-embodiment robot dataset (taxonomy seed)','dataset','https://github.com/google-deepmind/open_x_embodiment', false, 'Dataset, not a leaderboard')
) as v(domain_slug, slug, name, measures, metric, results_url, is_saturated, notes)
join domains d on d.slug = v.domain_slug
on conflict (slug) do nothing;
