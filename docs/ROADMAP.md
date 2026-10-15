# Collection planner goals

Version 1.10.0 implements the five usability changes requested for the collection
workbench. The remaining work is to turn feasible setups into performance-based
training recommendations.

| Goal | Current behavior | Remaining work |
| --- | --- | --- |
| Recognizable collection | Pictures, names, search and collection-specific sorting; saved sort preferences | More useful comparison views as performance metrics become available |
| Team Trials replacements | Start from an observed division/style and compare other owned trainees | Forecast an untrained runner's TT score and model interactions within the team |
| Requirements before trainee | Save skills and aptitudes without a trainee; search owned trainees, parent pairs and support skill sources | Rank by expected training results, support effects and scenario-specific deck quality |
| Internal resource tools | Skill-point, awakening-material and Grand Concert song budgets; manual balances and earning rates | Full Concert lesson/technique/shop strategy and verified resource acquisition routes |
| Original lineage linker | Visible sidebar entry, original local/remote searches and detailed inspectors; career-plan handoff | Use its inheritance probabilities and affinity scores directly in setup comparison |
| Multi-career goals | Editable plans, prerequisites, stop conditions and collection checks | Generate parent/grandparent training order, follow new career results and propose the next useful career |
| Competitive race planning | Recorded TT statistics and inherited lineage analysis | TT/CM race simulation, skill-value estimates and uncertainty-aware comparisons |

## Next development step

Add a scenario-aware training model to evaluate support effects at the owned
level and limit breaks, expected stat/skill-point output, event reliability and
the requested stat thresholds. Compare those estimates with recorded career
outcomes before using them to rank setups. Then add TT/CM race evaluation and
use both models to choose a training order for missing parents and runners.

The current shortlist ranks aptitude fit and skill access. It does not establish
that the first setup will train better or race faster than the next. Manual
goal completion remains available while result matching is expanded.
