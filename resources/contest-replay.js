/* Contest replay engine.
 * Scoring functions for all contest formats + virtual ranking computation.
 * Depends on window.renderRankingTable defined in contest-ranking.js.
 *
 * Entry point: window.initVirtualRanking(rankingData)
 */

(function ($) {
    'use strict';

    // subs: [[part_id, prob_id, pts, skip, t], ...] → {part_id: {prob_id: [{pts,skip,t}]}}
    function buildSubsIndex(subs) {
        var idx = {};
        for (var i = 0; i < subs.length; i++) {
            var s = subs[i], partId = s[0], probId = s[1];
            if (!idx[partId]) idx[partId] = {};
            if (!idx[partId][probId]) idx[partId][probId] = [];
            idx[partId][probId].push({ pts: s[2], skip: s[3], t: s[4] });
        }
        return idx;
    }

    function scoreICPC(probMap, problems, config, cutoff, duration, frozenSec) {
        var penaltyMin = (config && config.penalty !== undefined) ? config.penalty : 20;
        var freezePoint = duration - frozenSec;
        var inFrozen = frozenSec > 0 && cutoff > freezePoint;

        var score = 0, cumtimeMin = 0, tiebreakerMin = 0, totalPenalty = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var allSubs = probMap[pid] || [];
            if (!allSubs.length) continue;

            var preFreeze = inFrozen ? allSubs.filter(function (s) { return s.t <= freezePoint; }) : allSubs;
            var postFreeze = inFrozen ? allSubs.filter(function (s) { return s.t > freezePoint; }) : [];

            var maxPts = 0;
            for (var j = 0; j < preFreeze.length; j++) maxPts = Math.max(maxPts, preFreeze[j].pts);
            var firstAcTime = Infinity;
            if (maxPts > 0) {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (preFreeze[j].pts === maxPts && preFreeze[j].t < firstAcTime)
                        firstAcTime = preFreeze[j].t;
                }
            }
            var isSolved = (maxPts === prob.points && maxPts > 0);

            var tries = 0;
            if (isSolved) {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (!preFreeze[j].skip && preFreeze[j].t <= firstAcTime) tries++;
                }
                var dtMin = Math.floor(firstAcTime / 60);
                score += maxPts;
                cumtimeMin += dtMin;
                tiebreakerMin = Math.max(tiebreakerMin, dtMin);
                totalPenalty += (tries - 1) * penaltyMin;
            } else {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (!preFreeze[j].skip) tries++;
                }
            }

            if (!tries && !postFreeze.length) continue;

            var entry = {
                points: isSolved ? maxPts : 0,
                tries: tries,
                time: isSolved ? firstAcTime : 0,
            };
            if (postFreeze.length > 0 && !isSolved) {
                entry.is_frozen = true;
                for (var j = 0; j < postFreeze.length; j++) {
                    if (!postFreeze[j].skip) entry.tries++;
                }
            }
            formatData[String(pid)] = entry;
        }

        return { score: score, cumtime: Math.max(cumtimeMin + totalPenalty, 0), tiebreaker: tiebreakerMin, format_data: formatData };
    }

    function scoreVNOJ(probMap, problems, config, cutoff, duration, frozenSec) {
        var penaltyMin = (config && config.penalty !== undefined) ? config.penalty : 5;
        var penaltySec = penaltyMin * 60;
        var lso = !!(config && config.LSO);
        var freezePoint = duration - frozenSec;
        var inFrozen = frozenSec > 0 && cutoff > freezePoint;

        var score = 0, cumtime = 0, lastAc = 0, totalPenalty = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var allSubs = probMap[pid] || [];
            if (!allSubs.length) continue;

            var preFreeze = inFrozen ? allSubs.filter(function (s) { return s.t <= freezePoint; }) : allSubs;
            var postFreeze = inFrozen ? allSubs.filter(function (s) { return s.t > freezePoint; }) : [];

            var maxPts = 0;
            for (var j = 0; j < preFreeze.length; j++) maxPts = Math.max(maxPts, preFreeze[j].pts);
            var firstAcTime = Infinity;
            if (maxPts > 0) {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (preFreeze[j].pts === maxPts && preFreeze[j].t < firstAcTime)
                        firstAcTime = preFreeze[j].t;
                }
            }
            var isSolved = maxPts > 0;

            var prev = 0;
            if (isSolved) {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (!preFreeze[j].skip && preFreeze[j].t <= firstAcTime) prev++;
                }
                prev = Math.max(0, prev - 1);
                cumtime += firstAcTime;
                lastAc = Math.max(lastAc, firstAcTime);
                score += maxPts;
                totalPenalty += prev * penaltySec;
            } else {
                for (var j = 0; j < preFreeze.length; j++) {
                    if (!preFreeze[j].skip) prev++;
                }
            }

            var entry = { points: maxPts, time: isSolved ? firstAcTime : 0, penalty: prev };

            if (postFreeze.length > 0 && maxPts < prob.points) {
                var pendingCount = 0;
                for (var j = 0; j < postFreeze.length; j++) {
                    if (!postFreeze[j].skip) pendingCount++;
                }
                if (pendingCount > 0) entry.pending = pendingCount;
            }

            if (maxPts > 0 || prev > 0 || entry.pending) formatData[String(pid)] = entry;
        }

        var finalCumtime = lso ? Math.max(lastAc + totalPenalty, 0) : Math.max(cumtime + totalPenalty, 0);
        return { score: score, cumtime: finalCumtime, tiebreaker: lastAc, format_data: formatData };
    }

    function scoreAtCoder(probMap, problems, config) {
        var penaltyMin = (config && config.penalty !== undefined) ? config.penalty : 5;
        var penaltySec = penaltyMin * 60;

        var score = 0, cumtime = 0, totalPenalty = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var allSubs = probMap[pid] || [];
            if (!allSubs.length) continue;

            var maxPts = 0;
            for (var j = 0; j < allSubs.length; j++) maxPts = Math.max(maxPts, allSubs[j].pts);

            var firstAcTime = Infinity;
            if (maxPts > 0) {
                for (var j = 0; j < allSubs.length; j++) {
                    if (allSubs[j].pts === maxPts && allSubs[j].t < firstAcTime)
                        firstAcTime = allSubs[j].t;
                }
            }

            var wrongTries = 0;
            if (maxPts > 0) {
                for (var j = 0; j < allSubs.length; j++) {
                    if (!allSubs[j].skip && allSubs[j].t <= firstAcTime) wrongTries++;
                }
                wrongTries = Math.max(0, wrongTries - 1); // don't count the AC itself
                score += maxPts;
                cumtime = Math.max(cumtime, firstAcTime);
                totalPenalty += wrongTries * penaltySec;
            } else {
                for (var j = 0; j < allSubs.length; j++) {
                    if (!allSubs[j].skip) wrongTries++;
                }
            }

            if (maxPts > 0 || wrongTries > 0) {
                formatData[String(pid)] = { points: maxPts, time: maxPts > 0 ? firstAcTime : 0, penalty: wrongTries };
            }
        }

        return { score: score, cumtime: Math.max(cumtime + totalPenalty, 0), tiebreaker: 0, format_data: formatData };
    }

    function scoreIOI(probMap, problems, config) {
        var useCumtime = !!(config && config.cumtime);

        var score = 0, sumTime = 0, lastSolveTime = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var allSubs = probMap[pid] || [];
            if (!allSubs.length) continue;

            var maxPts = 0;
            for (var j = 0; j < allSubs.length; j++) maxPts = Math.max(maxPts, allSubs[j].pts);

            var firstAcTime = 0;
            if (maxPts > 0) {
                firstAcTime = Infinity;
                for (var j = 0; j < allSubs.length; j++) {
                    if (allSubs[j].pts === maxPts && allSubs[j].t < firstAcTime)
                        firstAcTime = allSubs[j].t;
                }
                score += maxPts;
                sumTime += firstAcTime;
                lastSolveTime = Math.max(lastSolveTime, firstAcTime);
            }

            formatData[String(pid)] = { points: maxPts, time: maxPts > 0 ? firstAcTime : 0 };
        }

        var finalCumtime = useCumtime ? sumTime : lastSolveTime;
        return { score: score, cumtime: Math.max(finalCumtime, 0), tiebreaker: lastSolveTime, format_data: formatData };
    }

    function scoreECOO(probMap, problems, config, duration) {
        var firstAcBonus = (config && config.first_ac_bonus !== undefined) ? config.first_ac_bonus : 10;
        var timeBonusInterval = (config && config.time_bonus !== undefined) ? config.time_bonus : 5;
        var useCumtime = !!(config && config.cumtime);

        var score = 0, cumtime = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var allSubs = probMap[pid] || [];
            if (!allSubs.length) continue;

            var lastSub = null, subCnt = 0;
            for (var j = 0; j < allSubs.length; j++) {
                if (!allSubs[j].skip) { subCnt++; lastSub = allSubs[j]; }
            }
            if (!lastSub) continue;

            var pts = lastSub.pts;
            var bonus = 0;
            if (subCnt === 1 && pts === prob.points) bonus += firstAcBonus;
            var remaining = duration - lastSub.t;
            if (remaining > 0) bonus += Math.floor(remaining / 60 / timeBonusInterval);

            score += pts + bonus;
            if (useCumtime) cumtime += lastSub.t;
            formatData[String(pid)] = { points: pts, time: lastSub.t, bonus: bonus };
        }

        return { score: score, cumtime: Math.max(cumtime, 0), tiebreaker: 0, format_data: formatData };
    }

    function scoreDefault(probMap, problems) {
        var score = 0, cumtime = 0;
        var formatData = {};

        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = prob.id;
            var subs = probMap[pid] || [];
            if (!subs.length) continue;

            var maxPts = 0, lastTime = 0;
            for (var j = 0; j < subs.length; j++) {
                if (subs[j].pts > maxPts) maxPts = subs[j].pts;
                if (subs[j].t > lastTime) lastTime = subs[j].t;
            }
            if (maxPts > 0) { score += maxPts; cumtime += lastTime; }
            formatData[String(pid)] = { points: maxPts, time: lastTime };
        }

        return { score: score, cumtime: Math.max(cumtime, 0), tiebreaker: 0, format_data: formatData };
    }

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

    function computeVirtualRanking(virtualSubsData, rankingData, elapsed) {
        var duration = virtualSubsData.duration;
        var frozenSec = virtualSubsData.frozen;
        var cutoff = Math.min(elapsed, duration);
        var contest = rankingData.contest;
        var problems = rankingData.problems;
        var format = contest.format;
        var config = contest.format_config || {};

        var filteredSubs = virtualSubsData.subs.filter(function (s) { return s[4] <= cutoff; });
        var subsIndex = buildSubsIndex(filteredSubs);

        function scoreOne(probMap) {
            if (format === 'icpc')    return scoreICPC(probMap, problems, config, cutoff, duration, frozenSec);
            if (format === 'vnoj')    return scoreVNOJ(probMap, problems, config, cutoff, duration, frozenSec);
            if (format === 'atcoder') return scoreAtCoder(probMap, problems, config);
            if (format === 'ioi') return scoreIOI(probMap, problems, config);
            if (format === 'ecoo')    return scoreECOO(probMap, problems, config, duration);
            return scoreDefault(probMap, problems);
        }

        var newParts = virtualSubsData.participations.map(function (p) {
            var scored = scoreOne(subsIndex[p.id] || {});
            return {
                id: p.id, score: scored.score, cumtime: scored.cumtime,
                tiebreaker: scored.tiebreaker, format_data: scored.format_data,
                is_disqualified: p.is_disqualified, virtual: p.virtual,
                rating: p.rating, user: p.user,
            };
        });

        if (rankingData.own) {
            var ownData = rankingData.own;
            var vProbMap = {};
            for (var j = 0; j < ownData.subs.length; j++) {
                var s = ownData.subs[j]; // [prob_id, pts, skip, t]
                if (s[3] > elapsed) break; // subs ordered by t
                if (!vProbMap[s[0]]) vProbMap[s[0]] = [];
                vProbMap[s[0]].push({ pts: s[1], skip: s[2], t: s[3] });
            }
            var vScored = scoreOne(vProbMap);
            newParts.push({
                id: ownData.id, score: vScored.score, cumtime: vScored.cumtime,
                tiebreaker: vScored.tiebreaker, format_data: vScored.format_data,
                is_disqualified: ownData.is_disqualified, virtual: ownData.virtual,
                rating: ownData.rating, user: ownData.user,
            });
        }

        sortAndRankParticipations(newParts);
        var isFrozenNow = frozenSec > 0 && cutoff > duration - frozenSec;
        return { contest: Object.assign({}, contest, { is_frozen: isFrozenNow }), problems: problems, participations: newParts };
    }

    function fetchReplayData(url, callback) {
        var cacheKey = 'replay_' + url;
        var cached = sessionStorage.getItem(cacheKey);
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

    window.initVirtualRanking = function (rankingData) {
        window.renderRankingTable(rankingData);

        var replayUrl = rankingData.contest && rankingData.contest.replay_url;
        if (!replayUrl) return;

        var isVirtual = !!rankingData.own;
        var virtualSubsData = null;
        var timerId = null;
        var manualElapsed = null; // null = auto mode
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

        // Creates the replay bar DOM; returns $endBtn. Does NOT wire data-dependent events.
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

        // Wires slider + button once virtualSubsData is available.
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
            // Auto-fetch, auto-start at current elapsed.
            fetchReplayData(replayUrl, function (data) {
                if (!data) return;
                virtualSubsData = data;
                var $endBtn = createBar(data.duration);
                wireEvents($endBtn);
                tick();
                timerId = setInterval(tick, 30000);
            });
        } else {
            // Show bar immediately using duration from page data; lazy-load subs on first touch.
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
