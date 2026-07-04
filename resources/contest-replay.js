/* Contest replay engine.
 * Scoring functions for all contest formats + virtual ranking computation.
 * Depends on window.renderRankingTable defined in contest-ranking.js.
 *
 * Entry point: window.initVirtualRanking(rankingData)
 */

(function ($) {
    'use strict';

    // ─── Per-problem state (accumulated as subs arrive in time order) ─────────

    function emptyState() {
        return { bestPts: 0, bestSubTime: 0, triesUpToAc: 0, totalTries: 0, lastValidSub: null, lastTime: 0, pending: 0 };
    }

    // Process one submission; mutates `s` (the state object for this problem).
    // Backend omits CE/IE/null subs, so every sub here is a scoring attempt.
    function updateState(s, sub) {
        if (sub.pts > s.bestPts) {
            s.bestPts     = sub.pts;
            s.bestSubTime = sub.t;
            s.triesUpToAc = s.totalTries + 1;
        }
        s.totalTries++;
        s.lastValidSub = sub;
        if (sub.t > s.lastTime) s.lastTime = sub.t;
    }

    // ─── Generic scorer ───────────────────────────────────────────────────────
    // Each format is expressed as a descriptor object produced by a factory in
    // FORMAT_DESCRIPTORS. scoreGeneric drives the single per-problem loop.
    //
    // Descriptor shape:
    //   probScore(st, prob)       → number — score contribution; return 0 if problem doesn't count
    //   probTime(st, prob)        → number — time contribution (called only when probScore > 0)
    //   probPenalty(st, prob)     → number — penalty contribution (called only when probScore > 0)
    //   probTiebreaker(st, prob)  → number — tiebreaker contribution (called only when probScore > 0)
    //   timeReducer               → 'sum' | 'max'
    //   tiebreakerReducer         → 'max'  | 'none'
    //   buildEntry(st, prob, scored) → object | null

    function scoreGeneric(probStates, problems, desc) {
        var score = 0, cumtime = 0, penalty = 0, tiebreaker = 0;
        var formatData = {};
        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi], pid = prob.id;
            var st = probStates[pid] || emptyState();
            if (!st.totalTries && !st.pending) continue;
            var s = desc.probScore(st, prob);
            if (s > 0) {
                score += s;
                var t = desc.probTime(st, prob);
                cumtime = desc.timeReducer === 'sum' ? cumtime + t : Math.max(cumtime, t);
                penalty += desc.probPenalty(st, prob);
                if (desc.tiebreakerReducer === 'max') {
                    tiebreaker = Math.max(tiebreaker, desc.probTiebreaker(st, prob));
                }
            }
            var entry = desc.buildEntry(st, prob, s > 0);
            if (entry) formatData[String(pid)] = entry;
        }
        return { score: score, cumtime: Math.max(cumtime + penalty, 0), tiebreaker: tiebreaker, format_data: formatData };
    }

    // ─── Format descriptor factories ─────────────────────────────────────────
    // Each factory takes (config, ctx) and returns a descriptor.
    // ctx = { duration } — runtime values not available in config.

    var FORMAT_DESCRIPTORS = {
        // ICPC: score = problems fully solved (bestPts must reach problem max).
        // cumtime = sum of AC times (minutes) + penalty per wrong try before AC (default 20 min).
        // tiebreaker = time of last AC (minutes). Frozen subs show as pending.
        icpc: function (cfg) {
            var penMin = cfg.penalty !== undefined ? cfg.penalty : 20;
            return {
                probScore:   function (st, prob) { return (st.bestPts === prob.points) ? st.bestPts : 0; },
                probTime:    function (st)       { return Math.floor(st.bestSubTime / 60); },
                probPenalty: function (st)       { return (st.triesUpToAc - 1) * penMin; },
                probTiebreaker: function (st)    { return Math.floor(st.bestSubTime / 60); },
                timeReducer: 'sum', tiebreakerReducer: 'max',

                buildEntry: function (st, prob, scored) {
                    var tries = scored ? st.triesUpToAc : (st.totalTries + st.pending);
                    var e = { points: st.bestPts, tries: tries, time: st.bestSubTime };
                    if (st.pending > 0 && !scored) e.is_frozen = true;
                    return e;
                },
            };
        },

        // VNOJ: score = best (max) score per problem; partial scores count.
        // cumtime = sum (or max if LSO) of best-score times + penalty per wrong try (default 5 min).
        // tiebreaker = time of last score-altering submission. Frozen subs show as pending.
        vnoj: function (cfg) {
            var penSec = (cfg.penalty !== undefined ? cfg.penalty : 5) * 60;
            var lso = !!cfg.LSO;
            return {
                probScore:      function (st)       { return st.bestPts; },
                probTime:       function (st)       { return st.bestSubTime; },
                probPenalty:    function (st)       { return (st.triesUpToAc - 1) * penSec; },
                probTiebreaker: function (st)       { return st.bestSubTime; },
                timeReducer: lso ? 'max' : 'sum', tiebreakerReducer: 'max',

                buildEntry: function (st, prob, scored) {
                    var prev = scored ? st.triesUpToAc - 1 : st.totalTries;
                    var e = { points: st.bestPts, time: st.bestSubTime, penalty: prev };
                    if (st.pending > 0 && st.bestPts < prob.points) e.pending = st.pending;
                    return e;
                },
            };
        },

        // AtCoder: score = max score per problem; partial scores count.
        // cumtime = max AC time across all problems + total penalty (wrong tries × default 5 min).
        // No tiebreaker beyond cumtime.
        atcoder: function (cfg) {
            var penSec = (cfg.penalty !== undefined ? cfg.penalty : 5) * 60;
            return {
                probScore:      function (st)       { return st.bestPts; },
                probTime:       function (st)       { return st.bestSubTime; },
                probPenalty:    function (st)       { return (st.triesUpToAc - 1) * penSec; },
                probTiebreaker: function ()         { return 0; },
                timeReducer: 'max', tiebreakerReducer: 'none',

                buildEntry: function (st, _, scored) {
                    var wrong = scored ? st.triesUpToAc - 1 : st.totalTries;
                    return { points: st.bestPts, time: st.bestSubTime, penalty: wrong };
                },
            };
        },

        // IOI: score = max score per problem; partial scores (batches) count, no penalty.
        // cumtime = sum of best-score times if config.cumtime=true, else 0.
        // tiebreaker = time of last score-altering submission.
        ioi: function (cfg) {
            var useCumtime = !!cfg.cumtime;
            return {
                probScore:      function (st)       { return st.bestPts; },
                probTime:       function (st)       { return useCumtime ? st.bestSubTime : 0; },
                probPenalty:    function ()         { return 0; },
                probTiebreaker: function (st)       { return st.bestSubTime; },
                timeReducer: 'sum', tiebreakerReducer: 'max',

                buildEntry: function (st) {
                    return { points: st.bestPts, time: st.bestSubTime };
                },
            };
        },

        // ECOO: score = last valid submission's score per problem + bonuses.
        //   first_ac_bonus (+10): if problem fully solved on very first submission.
        //   time_bonus: +1 point per N minutes remaining before contest end (default N=5).
        // cumtime = sum of last-sub times if config.cumtime=true, else ties not broken.
        ecoo: function (cfg, ctx) {
            var firstAcBonus      = cfg.first_ac_bonus !== undefined ? cfg.first_ac_bonus : 10;
            var timeBonusInterval = cfg.time_bonus     !== undefined ? cfg.time_bonus     : 5;
            var useCumtime = !!cfg.cumtime;
            var duration = ctx.duration;
            function calcBonus(st, prob) {
                var sub = st.lastValidSub, bonus = 0;
                if (st.totalTries === 1 && sub.pts === prob.points) bonus += firstAcBonus;
                var rem = duration - sub.t;
                if (rem > 0) bonus += Math.floor(rem / 60 / timeBonusInterval);
                return bonus;
            }
            return {
                probScore:      function (st, prob)  { return st.lastValidSub ? st.lastValidSub.pts + calcBonus(st, prob) : 0; },
                probTime:       function (st)       { return useCumtime ? st.lastValidSub.t : 0; },
                probPenalty:    function ()         { return 0; },
                probTiebreaker: function ()         { return 0; },
                timeReducer: 'sum', tiebreakerReducer: 'none',

                buildEntry: function (st, prob) {
                    var sub = st.lastValidSub;
                    return { points: sub.pts, time: sub.t, bonus: calcBonus(st, prob) };
                },
            };
        },

        // Default: score = max score per problem; partial scores count, no penalty.
        // cumtime = sum of last-submission times on problems with any score. No tiebreaker.
        default: function () {
            return {
                probScore:      function (st)       { return st.bestPts; },
                probTime:       function (st)       { return st.lastTime; },
                probPenalty:    function ()         { return 0; },
                probTiebreaker: function ()         { return 0; },
                timeReducer: 'sum', tiebreakerReducer: 'none',

                buildEntry: function (st) { return { points: st.bestPts, time: st.lastTime }; },
            };
        },
    };

    // ─── Ranking helpers ──────────────────────────────────────────────────────

    function sortAndRankParticipations(parts) {
        parts.sort(function (a, b) {
            var aDq = a.is_disqualified ? 1 : 0, bDq = b.is_disqualified ? 1 : 0;
            if (aDq !== bDq) return aDq - bDq;
            if (b.score !== a.score) return b.score - a.score;
            if (a.cumtime !== b.cumtime) return a.cumtime - b.cumtime;
            return a.tiebreaker - b.tiebreaker;
        });
        var rank = 0, delta = 1, lastKey = null;
        for (var i = 0; i < parts.length; i++) {
            var p = parts[i];
            var key = (p.is_disqualified ? 1 : 0) + '|' + p.score + '|' + p.cumtime + '|' + p.tiebreaker;
            if (key !== lastKey) { rank += delta; delta = 0; }
            delta++;
            p.rank = rank;
            lastKey = key;
        }
    }

    // ─── Core replay engine ───────────────────────────────────────────────────

    function computeVirtualRanking(virtualSubsData, rankingData, elapsed) {
        var duration  = virtualSubsData.duration;
        var frozenSec = virtualSubsData.frozen;
        var cutoff    = Math.min(elapsed, duration);
        var contest   = rankingData.contest;
        var problems  = rankingData.problems;
        var format    = contest.format;
        var config    = contest.format_config || {};
        var freezePoint = duration - frozenSec;

        // Single forward pass: build state[partId][probId]
        var state = {};
        var subs = virtualSubsData.subs;
        for (var i = 0; i < subs.length; i++) {
            var s = subs[i]; // [partId, probId, pts, t]
            if (s[3] > cutoff) continue;
            var partId = s[0], probId = s[1];
            if (!state[partId]) state[partId] = {};
            if (!state[partId][probId]) state[partId][probId] = emptyState();
            if (frozenSec > 0 && s[3] > freezePoint) {
                state[partId][probId].pending++;
            } else {
                updateState(state[partId][probId], { pts: s[2], t: s[3] });
            }
        }

        // Own subs for the virtual participant
        if (rankingData.own) {
            var ownData = rankingData.own;
            var ownId   = ownData.id;
            state[ownId] = {};
            for (var j = 0; j < ownData.subs.length; j++) {
                var os = ownData.subs[j]; // [probId, pts, t]
                if (os[2] > elapsed) break; // subs ordered by t
                var probId = os[0];
                if (!state[ownId][probId]) state[ownId][probId] = emptyState();
                updateState(state[ownId][probId], { pts: os[1], t: os[2] });
            }
        }

        var fac  = FORMAT_DESCRIPTORS[format] || FORMAT_DESCRIPTORS['default'];
        var desc = fac(config, { duration: duration });

        function scoreOne(partId) {
            return scoreGeneric(state[partId] || {}, problems, desc);
        }

        var newParts = virtualSubsData.participations.map(function (p) {
            var scored = scoreOne(p.id);
            return {
                id: p.id, score: scored.score, cumtime: scored.cumtime,
                tiebreaker: scored.tiebreaker, format_data: scored.format_data,
                is_disqualified: p.is_disqualified, virtual: p.virtual,
                rating: p.rating, user: p.user,
            };
        });

        if (rankingData.own) {
            var ownData = rankingData.own;
            var scored  = scoreOne(ownData.id);
            newParts.push({
                id: ownData.id, score: scored.score, cumtime: scored.cumtime,
                tiebreaker: scored.tiebreaker, format_data: scored.format_data,
                is_disqualified: ownData.is_disqualified, virtual: ownData.virtual,
                rating: ownData.rating, user: ownData.user,
            });
        }

        sortAndRankParticipations(newParts);
        var isFrozenNow = frozenSec > 0 && cutoff > freezePoint;
        return { contest: Object.assign({}, contest, { is_frozen: isFrozenNow }), problems: problems, participations: newParts };
    }

    // ─── Fetch helpers ────────────────────────────────────────────────────────

    function fetchReplayData(url, callback) {
        var cacheKey = 'replay_' + url;
        var cached   = sessionStorage.getItem(cacheKey);
        if (cached) {
            try { callback(JSON.parse(cached)); return; } catch (e) { sessionStorage.removeItem(cacheKey); }
        }
        $.ajax({ url: url, dataType: 'json' })
            .done(function (data) {
                try { sessionStorage.setItem(cacheKey, JSON.stringify(data)); } catch (e) {}
                callback(data);
            })
            .fail(function () { callback(null); });
    }

    function fmtHMS(s) {
        s = Math.floor(Math.max(0, s));
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
        return (h ? h + ':' : '') + (h && m < 10 ? '0' : '') + m + ':' + (sec < 10 ? '0' : '') + sec;
    }

    // ─── Public entry point ───────────────────────────────────────────────────

    window.initVirtualRanking = function (rankingData) {
        window.renderRankingTable(rankingData);

        var replayUrl = rankingData.contest && rankingData.contest.replay_url;
        if (!replayUrl) return;

        var isVirtual      = !!rankingData.own;
        var virtualSubsData = null;
        var timerId        = null;
        var manualElapsed  = null; // null = auto mode
        var $slider = null, $timeLabel = null;

        function getLiveElapsed() {
            return (Date.now() / 1000) - rankingData.own.real_start;
        }

        function renderAt(elapsed) {
            window.renderRankingTable(computeVirtualRanking(virtualSubsData, rankingData, elapsed));
        }

        function updateBar(elapsed, duration) {
            if (!$slider) return;
            $slider.val(Math.floor(elapsed));
            $timeLabel.text(fmtHMS(elapsed) + ' / ' + fmtHMS(duration));
        }

        function createBar(duration) {
            var $bar = $('<div>').css({
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '6px 0', marginBottom: '8px', fontSize: '13px',
            });
            $slider = $('<input>').attr({ type: 'range', min: 0, max: Math.floor(duration), step: 1 })
                .css({ flex: '1', cursor: 'pointer' });
            $timeLabel = $('<span>').css({ minWidth: '110px', fontFamily: 'monospace' });
            var $endBtn = $('<button>').text(isVirtual ? 'Live' : 'End').css({ fontSize: '12px', padding: '2px 8px' });
            $bar.append($('<span>').text('⏱'), $slider, $timeLabel, $endBtn);
            $('#ranking-container').before($bar);
            return $endBtn;
        }

        function wireEvents($endBtn) {
            $slider.on('input', function () {
                manualElapsed = parseInt(this.value);
                if (timerId) { clearInterval(timerId); timerId = null; }
                updateBar(manualElapsed, virtualSubsData.duration);
                renderAt(manualElapsed);
            });
            $endBtn.on('click', function () {
                if (isVirtual) {
                    manualElapsed = null;
                    if (!timerId) timerId = setInterval(tick, 30000);
                } else {
                    manualElapsed = Math.floor(virtualSubsData.duration);
                }
                tick();
            });
        }

        function tick() {
            if (!virtualSubsData) return;
            var elapsed = manualElapsed !== null
                ? manualElapsed
                : (isVirtual ? Math.min(getLiveElapsed(), virtualSubsData.duration) : virtualSubsData.duration);
            updateBar(elapsed, virtualSubsData.duration);
            renderAt(elapsed);
            if (isVirtual && manualElapsed === null && elapsed >= virtualSubsData.duration) {
                clearInterval(timerId); timerId = null;
            }
        }

        if (isVirtual) {
            fetchReplayData(replayUrl, function (data) {
                if (!data) return;
                virtualSubsData = data;
                var $endBtn = createBar(data.duration);
                wireEvents($endBtn);
                tick();
                timerId = setInterval(tick, 30000);
            });
        } else {
            var $endBtn = createBar(rankingData.contest.replay_duration);
            updateBar(rankingData.contest.replay_duration, rankingData.contest.replay_duration);
            $slider.one('mousedown touchstart', function () {
                fetchReplayData(replayUrl, function (data) {
                    if (!data) return;
                    virtualSubsData = data;
                    $slider.attr('max', Math.floor(data.duration));
                    wireEvents($endBtn);
                    manualElapsed = parseInt($slider.val());
                    updateBar(manualElapsed, data.duration);
                    renderAt(manualElapsed);
                });
            });
        }
    };

})(jQuery);
