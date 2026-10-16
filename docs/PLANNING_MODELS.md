# Planning models and checks

Version 1.14 adds functional planning workflows for the six collection-planner
goals. Predictions are community models, not official game outcomes. The UI
keeps recorded results, model ranges and unavailable information distinct.
No browser engine, game automation or proprietary game dataset is bundled.

## Career forecasts

`uma_workbench/career.py` runs seeded turn-by-turn careers. Each turn draws a
support board, considers all five practices with their actual participants,
updates bond/facilities/energy and chooses a practice, rest or outing. Practice
gains use the existing level-aware MDB training formula described in
[TRAINING_MODEL.md](TRAINING_MODEL.md). The model respects stat caps and the
post-1200 practice conversion. Required race calendars come from local routes;
optional race turns are entered in Career assumptions.

Energy policy, event frequency/rewards, race rewards and race success/continues
are explicit assumptions. Failed required races can end a sample. Detached
event logs are not used to calibrate a different trainee/scenario. A replay of
the exact game's event scheduler, all support events and every scenario mechanic
is not available from the local export alone.

Unity team and Trackblazer shop additions are editable aggregate assumptions,
not complete emulations of their teammates or shops. Grand Concert can apply a
saved purchase schedule, decoding direct stat, recovery and per-practice bonuses
from the local lesson tables. This schedule assumes the entered purchases become
available. It does not claim to predict future random shop offers.

Starting blue stats use the community-observed 5/12/21 points per 1/2/3-star
factor. Red starting aptitudes use the original linker. The two inspiration
opportunities use the original individual-affinity coefficients and pink proc
rates; direct white-skill rates use the original 3/6/9% model. Inheritance,
practice hint access and support-event completion remain probabilities. Desired
skills must have a source and affordable positive prerequisites; unknown prices
are not treated as free. Forecasts report acquired-skill frequencies.

Ranges are sample outcome ranges under the chosen assumptions, not confidence
intervals proving model accuracy. A forecast saved to team planning is invalidated
when its plan inputs, game database or imported collection snapshots change.
Setup search first screens the existing bounded collection shortlist and then
compares career target rates and race speed. It does not establish a global
optimum over every deck and parent combination.

**Check recorded careers** compares an earlier and later snapshot with the same
explicit career identity and at least twelve turns of separation. The later
state is withheld, event samples are not learned from that held-out career, and
per-stat mean absolute errors are reported. Different actual decisions still
affect the comparison. With no suitable pairs the result says so; completed
veterans with similar names/decks are not substituted as validation pairs.

## Race comparisons and teams

`uma_workbench/racing.py` implements a seeded phase/energy comparison. It includes
style-dependent target speed, acceleration, distance/surface/style aptitudes,
mood, post-1200 stat conversion, stamina exhaustion, supported skill conditions
and effects, and approximate blocking between runners. Field win rates depend
on the runners and opponents entered. They are not universal TT or CM win rates.

Static course restrictions are checked before assigning skill value. Unknown
conditions/effects remain unranked and are counted in the race report. Full
course geometry, all positional mechanics, all conditional skill timing and
every unique/debuff are not reproduced. Course-dependent skill value is an
estimate within this coverage, not a universal tier list.

TT assignment enforces fifteen slots, three per division, globally unique
characters and distinct styles within each division. CM selects three unique
characters for the entered course. Candidates include retained career forecasts
when requested. Minimum-cost flow solves the supplied individual candidate
assignment; bounded coordinate refinement then compares joint fields with common
random seeds. The complete interaction objective is not globally exhaustive.

TT base-point projections require at least three distinct recorded runner
averages with three observations each and a positive fitted relationship in
that division. No calibrated points are invented for an unsupported division.
Recorded opponent quality and race context can confound that fit. Race index
and times remain model comparisons, not official point calculations.

## Projects and progress

`uma_workbench/projects.py` generates an acyclic grandparent/parent/runner project
from a saved requirement-first plan. Suitable existing parents are reused.
Missing preparation stages carry structured result-spark targets. New imported
veterans are checked against character, skills, stats, aptitudes and result sparks;
matching stages complete and bind their exact veteran copies into dependent plans.
Attempt counts compare against the collection present when the project started.
Arbitrary natural-language stop rules are not silently interpreted as structured
criteria. A next-career suggestion must have completed prerequisites and remain
within its attempt limit. Project generation is atomic and detects stale edits;
repeating generation for a converted root reuses its existing project.

## References and resources

Skill profiles use local names/descriptions, effects, costs, positive prerequisites
and owned trainee/support sources. Contextual rankings explain when the model
cannot value a skill. Support comparisons use exported levels/limit breaks and
practice contributions; a single-card marginal comparison is not a complete-deck
rating. Trainee rankings use collection setup search.

Resource advice ranks awakening unlocks by required/relevant skills and expected
effort. Item balances and minutes per entry are entered by the player. Race routes
use `single_mode_program` and `single_mode_reward_set`, including qualifying finish
brackets and millionth probabilities, excluding campaign bonus rows. Missing
routes remain unknown. Separate item run totals form a conservative budget;
one race can yield several items. No live banner recommendation or invented
currency yield is presented.

## Grand Concert

The shop planner takes five balances, currently offered lessons, wanted songs,
bought items, current energy, turn and practices left. It searches affordable
subsets, values decoded permanent bonuses over remaining practices and reserves
for wanted songs. Only selected offers may be bought. Costs and recognised
effects come from local tables; unrecognised effects are disclosed. The song
target/deadline comes from the local Concert schedule.

Purchase recording changes only the app's local budget. It rejects stale balances
and prevents recording the same recommendation twice. Re-check offers after an
in-game refresh. A purchase schedule can be saved into a career plan. Future
offer distributions, lesson refresh chains and full live bonuses remain outside
the forecast; do not interpret the bounded shopping search as an exact global
Grand Concert strategy.

## Formula provenance

The independently written phase/energy and performance comparisons were checked
against mathematical relationships in the primary community implementation at
`mee1080/umasim` commit `cf9366f6a487bd8f197b53d8a11981207beb9f6c`:

- [Race equations](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/race/src/commonMain/kotlin/io/github/mee1080/umasim/race/calc2/RaceState.kt)
- [Coefficient definitions](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/race/src/commonMain/kotlin/io/github/mee1080/umasim/race/data/constants.kt)
- [Concert mechanics reference](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/core/src/commonMain/kotlin/io/github/mee1080/umasim/scenario/live/LiveCalculator.kt)

No external simulator source or third-party game dataset is copied or bundled.
