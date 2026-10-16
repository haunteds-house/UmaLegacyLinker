# Collection planner goals

Version 1.13.0 replaces the embedded website with a native roster and lineage
planner. No browser engine is loaded or shipped. Collection and lineage data
stay local; optional artwork downloads are cached separately. A working roster
viewer and setup shortlist do not complete the account-optimization goals.

| Goal | Available now | Remaining work |
| --- | --- | --- |
| English Windows app based on the fork | Native Qt app; English source UI; names, outfits and pictures; original lineage linker retained | Continue usability checks with real collections |
| Collection and local data | Import owned trainees, supports, veterans and race exports; watch umadump output without changing the extractor | Broaden supported export layouts when new formats appear |
| Recognizable roster | Native veteran cards, ratings/dates, stats, skills, sparks and ancestry; shared sorting and aptitude/spark/skill filters | Contextual side-by-side comparisons of runners, skills and supports |
| Native lineage planning | Exact owned parent copies, combined six-member sparks, starting aptitudes, canonical compatibility and recorded G1 bonuses; career-plan handoff | Feed full inheritance probabilities and affinity into joint setup ranking, including reusable parent loops |
| Requirements before trainee | Save skills and aptitudes without a trainee; search owned trainees, parent pairs and five owned supports plus one rental | Rank by validated career and race outcomes rather than source coverage and practice estimates |
| Team Trials | Recorded base scores, skill activations, measured 15-runner shortlist and replacement plans across owned trainees | Predict untrained runners, optimize the full team and account for teammate interactions and race conditions |
| Champions Meeting | Course/role requirements can be stored in a career plan | Dedicated event planning, opponent/skill evaluation and race simulation |
| Career guidance | Support-level effects and optional practice comparisons; prior completed careers shown as references | Full-career energy/rest, events, races, scenario mechanics and training decisions; validate final-stat forecasts |
| Multi-generation projects | Manual parent/grandparent/runner plans, prerequisites, stop conditions, collection checks, remove and restore | Generate the parent-to-runner career order, detect useful new results, update dependent plans and recommend the next career |
| Readable game reference and recommendations | Named collection details; advanced raw MDB browser | Internal readable skill/card profiles, contextual rankings and collection-specific explanations |
| Currency and account resources | Skill-point and awakening budgets, manual balances/rates and saving milestones | Verified earning routes, upgrade priorities, spending recommendations and useful time/currency comparisons |
| Grand Concert | Internal song costs, effects and separate resource deficits | Lesson/technique/shop strategy, current offerings and training integration |
| Windows distribution | Automated functional, layout, packaged native-roster and no-browser checks; ZIP checksum | Investigate the reported antivirus detection using its exact threat name/file; publisher signing and malware scan coverage remain outstanding |

## Development order

1. Finish the native roster workflow and its Windows validation. Keep technical
   detail behind the relevant inspectors and preserve the original linker.
2. Extend the practice model to whole careers, including energy, recovery,
   events, races and scenario decisions. Validate against completed exports.
3. Add TT/CM outcome evaluation, then use it to compare complete teams and
   choose among trainable replacements. Show uncertainty and assumptions.
4. Connect those comparisons to generated multi-generation projects, automatic
   progress checks and a clear next useful career.
5. Complete readable references, contextual rankings, resource advice and
   Grand Concert strategy using the same collection and career models.

The current setup shortlist combines aptitude fit, skill access and optional
practice output. It does not establish which setup wins a race or finishes a
career with the best stats. Plan completion remains manual. Removing the browser
does not establish that an antivirus detection was a false positive.
