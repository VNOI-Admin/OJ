/* Contest ranking frontend renderer.
 * Replaces the server-side display_user_problem / display_participation_result
 * HTML rendering with a client-side equivalent that works for all contest formats.
 *
 * Entry point: window.renderRankingTable(data)
 *   data — the JSON object returned by the ?data endpoint on the contest ranking view.
 */

(function ($) {
    'use strict';

    // ─── Utilities ───────────────────────────────────────────────────────────

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Replicates nice_repr(timedelta(seconds=X), 'noday') from Python.
    function fmtTime(seconds) {
        seconds = Math.max(0, Math.floor(seconds));
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = seconds % 60;
        return pad2(h) + ':' + pad2(m) + ':' + pad2(s);
    }

    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    // Replicates Django's floatformat(pts, -precision).
    function fmtPoints(pts, precision) {
        if (pts === null || pts === undefined) return '0';
        if (precision === 0) return String(Math.round(pts));
        return parseFloat(parseFloat(pts).toFixed(precision)).toString();
    }

    // Returns the base CSS state class for a score.
    function baseStateClass(pts, maxPts) {
        if (!pts) return 'failed-score';
        if (pts === maxPts) return 'full-score';
        return 'partial-score';
    }

    // ─── Rating helpers ───────────────────────────────────────────────────────
    // Constants are loaded from backend via contest.rating_config to stay in sync
    // with judge/ratings.py.

    var _ratingConfig = null;

    function initRatingConfig(config) {
        _ratingConfig = config;
    }

    function ratingLevel(r) {
        if (!_ratingConfig) return 0;
        var values = _ratingConfig.values;
        for (var i = 0; i < values.length; i++) {
            if (r < values[i]) return i;
        }
        return values.length;
    }

    function ratingProgress(r) {
        if (!_ratingConfig) return 0;
        var values = _ratingConfig.values;
        var lvl = ratingLevel(r);
        if (lvl >= values.length) return 1.0;
        var prev = lvl === 0 ? 0 : values[lvl - 1];
        return (r - prev) / (values[lvl] - prev);
    }

    function ratingHtml(r) {
        if (r === null || r === undefined || !_ratingConfig) return '';
        var lvl = ratingLevel(r);
        var cls = _ratingConfig.classes[lvl];
        var name = _ratingConfig.names[lvl];
        var height = Math.round(ratingProgress(r) * 16 * 100) / 100;
        return '<span class="rate-group" title="' + escapeHtml(name) + '">' +
            '<svg class="rate-box ' + cls + '" viewBox="0 0 16 16">' +
            '<circle cx="8" cy="8" r="7"></circle>' +
            '<path clip-path="url(#rating-clip)" d="M0 16v-' + height + 'h16 0v16z"></path>' +
            '</svg>' +
            '<span class="rating ' + cls + '">' + r + '</span>' +
            '</span>';
    }

    // ─── First-solve / Total-AC computation ──────────────────────────────────

    function computeFirstSolvesAndTotalAC(participations, problems, contest) {
        var firstSolves = {};
        var totalAC = {};
        var cfg = contest.format_config || {};

        // Legacy IOI suppresses first-solve when time display is off.
        var suppressFirstSolve = (contest.format === 'ioi' || contest.format === 'ioi16') &&
                                 !cfg.cumtime && !cfg.last_score_altering;

        for (var pi = 0; pi < problems.length; pi++) {
            var problem = problems[pi];
            var pid = String(problem.id);
            firstSolves[pid] = null;
            totalAC[pid] = 0;
            var minTime = null;

            for (var ri = 0; ri < participations.length; ri++) {
                var p = participations[ri];
                var entry = (p.format_data || {})[pid];
                if (!entry) continue;

                var pts = entry.points || 0;
                var t   = entry.time   || 0;

                if (pts === problem.points) {
                    totalAC[pid]++;
                    if (!suppressFirstSolve && p.virtual === 0 && (minTime === null || t < minTime)) {
                        minTime = t;
                        firstSolves[pid] = p.id;
                    }
                }
            }
        }

        return { firstSolves: firstSolves, totalAC: totalAC };
    }

    // ─── Shared rendering helpers ────────────────────────────────────────────

    function makeSubmissionUrl(meta, problemCode) {
        return meta.contest.url_templates.problem_submissions
            .replace('__USERNAME__', meta.username)
            .replace('__PROBLEM__', problemCode);
    }

    function makeAllSubmissionsUrl(meta) {
        return meta.contest.url_templates.all_submissions
            .replace('__USERNAME__', meta.username);
    }

    // Returns the pretest CSS prefix for a problem cell.
    function pretestPrefix(meta, problem) {
        return (meta.contest.run_pretests_only && problem.is_pretested) ? 'pretest-' : '';
    }

    // Builds the state CSS class string common to all problem cells.
    function problemStateClass(entry, problem, isFirst, meta, extraPrefix) {
        return (extraPrefix || '') +
               pretestPrefix(meta, problem) +
               (isFirst ? 'first-solve ' : '') +
               baseStateClass(entry.points, problem.points);
    }

    // Wraps inner HTML in a standard problem <td><a>...</a></td>.
    function wrapProblemCell(state, url, innerHtml) {
        return '<td class="' + state + '"><a href="' + escapeHtml(url) + '">' +
               innerHtml + '</a></td>';
    }

    // Standard result cell: score with optional cumtime.
    function standardResultCell(participation, meta, showTime) {
        var url = makeAllSubmissionsUrl(meta);
        return '<td class="user-points"><a href="' + escapeHtml(url) + '">' +
            escapeHtml(fmtPoints(participation.score, meta.contest.points_precision)) +
            '<div class="solving-time">' +
            (showTime !== false ? escapeHtml(fmtTime(participation.cumtime)) : '') +
            '</div></a></td>';
    }

    // Standard problem cell: points + optional extra HTML + time.
    // Used by default, atcoder, ecoo, legacy-ioi, and vnoj (non-pending).
    function standardProblemCell(entry, problem, participationId, firstSolves, meta, opts) {
        if (!entry) return '<td></td>';
        var pid = String(problem.id);
        var isFirst = firstSolves[pid] === participationId;
        var url = makeSubmissionUrl(meta, problem.code);

        var pointsHtml = escapeHtml(fmtPoints(entry.points, meta.contest.points_precision));
        var extraHtml = opts && opts.extraHtml ? opts.extraHtml : '';
        var showTime = !(opts && opts.showTime === false);
        var timeHtml = showTime ? escapeHtml(fmtTime(entry.time)) : '';
        var wrapDiv = opts && opts.wrapDiv;

        var inner = wrapDiv
            ? '<div>' + pointsHtml + extraHtml + '</div>'
            : pointsHtml + extraHtml;
        inner += '<div class="solving-time">' + timeHtml + '</div>';

        var state = problemStateClass(entry, problem, isFirst, meta);
        return wrapProblemCell(state, url, inner);
    }

    // Builds a red penalty annotation: " (N)"
    function penaltyHtml(value) {
        if (!value) return '';
        return '<small style="color:red"> (' + escapeHtml(fmtPoints(value, 0)) + ')</small>';
    }

    // ─── Format renderers ─────────────────────────────────────────────────────
    // Each renderer provides:
    //   renderProblemCell(entry, problem, participationId, firstSolves, meta)
    //   renderResultCell(participation, meta)
    //   extraHeaderCols(meta)   — extra <th>s after Points (default: '')
    //   colspanTotalAC          — colspan for "Total AC" label (default: 3)

    // ── Default ──────────────────────────────────────────────────────────────
    var defaultRenderer = {
        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            return standardProblemCell(entry, problem, participationId, firstSolves, meta);
        },
        renderResultCell: function (participation, meta) {
            return standardResultCell(participation, meta);
        },
    };

    // ── ICPC ─────────────────────────────────────────────────────────────────
    var icpcRenderer = {
        extraHeaderCols: function (meta) {
            return '<th class="penalty">' + escapeHtml(meta.penaltyLabel) + '</th>';
        },
        colspanTotalAC: 4,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var tries = entry.tries || 0;
            if (tries === 0) return '<td></td>';

            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, problem.code);

            var triesText = tries + ' ' + (tries === 1 ? 'try' : 'tries');
            var extraPrefix = entry.is_frozen ? 'pending ' : '';
            var state = problemStateClass(entry, problem, isFirst, meta, extraPrefix);

            if (!entry.points) {
                return wrapProblemCell(state, url, escapeHtml(triesText));
            }

            return wrapProblemCell(state, url,
                '<div class="solving-time-minute">' + Math.floor(entry.time / 60) + '</div>' +
                '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                escapeHtml(triesText));
        },

        renderResultCell: function (participation, meta) {
            var url = makeAllSubmissionsUrl(meta);
            return '<td class="user-points">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(participation.score, meta.contest.points_precision)) +
                '</a></td>' +
                '<td class="user-penalty">' +
                escapeHtml(Math.round(participation.cumtime)) +
                '</td>';
        },
    };

    // ── Legacy IOI (ioi) ─────────────────────────────────────────────────────
    var legacyIoiRenderer = {
        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            var cfg = meta.contest.format_config || {};
            var showTime = cfg.cumtime || cfg.last_score_altering;
            return standardProblemCell(entry, problem, participationId, firstSolves, meta, {
                showTime: !!showTime,
            });
        },
        renderResultCell: function (participation, meta) {
            var cfg = meta.contest.format_config || {};
            var showTime = cfg.cumtime || cfg.last_score_altering;
            return standardResultCell(participation, meta, !!showTime);
        },
    };

    // ── IOI 2016+ (ioi16) ────────────────────────────────────────────────────
    var ioiRenderer = $.extend({}, legacyIoiRenderer);

    // ── AtCoder ───────────────────────────────────────────────────────────────
    var atcoderRenderer = {
        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            return standardProblemCell(entry, problem, participationId, firstSolves, meta, {
                extraHtml: penaltyHtml(entry && entry.penalty),
            });
        },
        renderResultCell: defaultRenderer.renderResultCell,
    };

    // ── VNOJ ──────────────────────────────────────────────────────────────────
    var vnojRenderer = {
        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pending = entry.pending || 0;

            if (!pending) {
                return standardProblemCell(entry, problem, participationId, firstSolves, meta, {
                    extraHtml: penaltyHtml(entry.penalty),
                    wrapDiv: true,
                });
            }

            // Pending path: post-freeze submissions hidden
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, problem.code);
            var state = problemStateClass(entry, problem, isFirst, meta, 'pending ');

            var pendingBadge = '<small style="color:black;"> [' + escapeHtml(String(pending)) + ']</small>';
            var ptsStr = (!entry.points && !entry.penalty)
                ? '?'
                : escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) + '?';

            return wrapProblemCell(state, url,
                '<div>' + ptsStr + pendingBadge + '</div>' +
                '<div class="solving-time">?</div>');
        },
        renderResultCell: defaultRenderer.renderResultCell,
    };

    // ── ECOO ──────────────────────────────────────────────────────────────────
    var ecooRenderer = {
        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            var bonusHtml = (entry && entry.bonus)
                ? '<small> +' + escapeHtml(fmtPoints(entry.bonus, 0)) + '</small>'
                : '';
            return standardProblemCell(entry, problem, participationId, firstSolves, meta, {
                extraHtml: bonusHtml,
            });
        },
        renderResultCell: function (participation, meta) {
            var cfg = meta.contest.format_config || {};
            return standardResultCell(participation, meta, !!cfg.cumtime);
        },
    };

    var RENDERERS = {
        'default':    defaultRenderer,
        'icpc':       icpcRenderer,
        'ioi':        legacyIoiRenderer,
        'ioi16':      ioiRenderer,
        'atcoder':    atcoderRenderer,
        'vnoj':       vnojRenderer,
        'ecoo':       ecooRenderer,
    };

    // ─── Table builder ────────────────────────────────────────────────────────

    function getRenderer(formatName) {
        var renderer = RENDERERS[formatName] || RENDERERS['default'];
        // Fill in defaults for optional properties.
        return {
            extraHeaderCols: renderer.extraHeaderCols || function () { return ''; },
            colspanTotalAC: renderer.colspanTotalAC || 3,
            renderProblemCell: renderer.renderProblemCell,
            renderResultCell: renderer.renderResultCell,
        };
    }

    function buildHeader(contest, problems, renderer) {
        var isICPC = contest.format === 'icpc';
        var html = '<thead><tr>';
        html += '<th class="header rank">' + escapeHtml(contest.rank_header || 'Rank') + '</th>';
        html += '<th class="header username">Username</th>';
        html += '<th class="header points">Points</th>';
        html += renderer.extraHeaderCols({ contest: contest, penaltyLabel: 'Penalty' });
        for (var i = 0; i < problems.length; i++) {
            var prob = problems[i];
            html += '<th class="points header">' +
                '<a href="' + escapeHtml(prob.url) + '">' +
                escapeHtml(prob.label);
            if (!isICPC) {
                html += '<div class="point-denominator">' + escapeHtml(String(prob.points)) + '</div>';
            }
            html += '<div class="problem-code" style="display:none;">' + escapeHtml(prob.code) + '</div>';
            html += '</a></th>';
        }
        if (contest.has_rating) {
            html += '<th class="rating-column">Rating</th>';
        }
        html += '</tr></thead>';
        return html;
    }

    function buildAdminOps(participation, contest) {
        if (!contest.can_edit) return '';
        var p = participation;
        var disqLabel = p.is_disqualified ? 'Un-Disqualify' : 'Disqualify';
        var disqClass = p.is_disqualified ? 'un-disqualify-participation' : 'disqualify-participation';
        var disqIcon  = p.is_disqualified ? 'fa-undo' : 'fa-trash';

        var html = '<span class="contest-participation-operation">' +
            '<a href="#" title="' + escapeHtml(disqLabel) + '" class="' + disqClass + '"' +
            ' data-participation-id="' + p.id + '"' +
            ' data-action-url="' + escapeHtml(contest.disqualify_url) + '">' +
            '<i class="fa ' + disqIcon + ' fa-fw"></i></a>';

        if (contest.can_change_participation) {
            var adminUrl = contest.admin_url_template.replace('__ID__', p.id);
            html += '<a href="' + escapeHtml(adminUrl) + '" title="Admin" class="edit-participation">' +
                '<i class="fa fa-cog fa-fw"></i></a>';
        }
        html += '</span>';
        return html;
    }

    function buildUserLink(u) {
        var html = '<span class="' + escapeHtml(u.css_class) + '">' +
            '<a href="' + escapeHtml(u.url) + '" style="display: inline-block;">' +
            escapeHtml(u.display_name) + '</a>';
        if (u.badge) {
            html += '<img src="' + escapeHtml(u.badge.mini) + '"' +
                ' title="' + escapeHtml(u.badge.name) + '"' +
                ' style="height: 1em; width: auto; margin-left: 0.25em;" />';
        }
        html += '</span>';
        return html;
    }

    function buildUserRow(participation, problems, firstSolves, contest, renderer) {
        var p = participation;
        var u = p.user;

        var rowClass = p.is_disqualified ? ' class="disqualified"' : '';
        var html = '<tr id="user-' + escapeHtml(u.username) + '"' + rowClass + '>';

        // Rank cell
        var rankDisplay;
        if (contest.mode === 'participation') {
            if (p.virtual === 0) {
                var liveUrl = escapeHtml(contest.ranking_url + '#!' + u.username);
                rankDisplay = '<a href="' + liveUrl + '">Live</a>';
            } else {
                rankDisplay = escapeHtml(String(p.virtual));
            }
        } else {
            rankDisplay = escapeHtml(String(p.rank));
        }
        html += '<td>' + rankDisplay + '</td>';

        // Username cell
        html += '<td class="user-name"><div>';
        html += '<div style="float:left">';
        html += buildUserLink(u);

        if (p.virtual > 0) {
            var virtualTitle = p.virtual + ' virtual participation' + (p.virtual > 1 ? 's' : '') + ' of this user';
            html += '<sup class="virtual-participation" title="' + escapeHtml(virtualTitle) + '">' +
                '[' + p.virtual + ']</sup>';
        }

        html += '<div class="personal-info"><span>' + escapeHtml(u.name || '') + '</span></div>';
        html += '</div>';

        // Right float (admin ops, org)
        html += '<div style="float:right">';
        html += buildAdminOps(p, contest);
        html += '<div class="personal-info" style="text-align: right;">';
        if (u.organization) {
            html += '<span class="organization">' +
                '<a href="' + escapeHtml(u.organization.url) + '">' +
                escapeHtml(u.organization.short_name) + '</a></span>';
        }
        html += '</div></div>';
        html += '</div></td>';

        // Build meta for renderer
        var meta = {
            contest: contest,
            username: u.username,
        };

        // Result cell(s)
        html += renderer.renderResultCell(p, meta);

        // Problem cells
        for (var pi = 0; pi < problems.length; pi++) {
            var prob = problems[pi];
            var pid = String(prob.id);
            var entry = (p.format_data || {})[pid] || null;
            html += renderer.renderProblemCell(entry, prob, p.id, firstSolves, meta);
        }

        // Rating cell
        if (contest.has_rating) {
            html += '<td class="rating-column">' + ratingHtml(p.rating) + '</td>';
        }

        html += '</tr>';
        return html;
    }

    function buildTotalACRow(problems, totalAC, colspan, hasRating) {
        var html = '<tr><td colspan="' + colspan + '">Total AC</td>';
        for (var i = 0; i < problems.length; i++) {
            var prob = problems[i];
            var pid = String(prob.id);
            var label = escapeHtml(prob.label);
            html += '<td class="total-ac" id="' + label + '-total">' +
                escapeHtml(String(totalAC[pid] || 0)) + '</td>';
        }
        if (hasRating) html += '<td></td>';
        html += '</tr>';
        return html;
    }

    // ─── Public entry point ───────────────────────────────────────────────────

    window.renderRankingTable = function (data) {
        var contest = data.contest;
        var problems = data.problems;
        var participations = data.participations;

        if (contest.rating_config) {
            initRatingConfig(contest.rating_config);
        }

        var renderer = getRenderer(contest.format);
        var result = computeFirstSolvesAndTotalAC(participations, problems, contest);
        var firstSolves = result.firstSolves;
        var totalAC = result.totalAC;

        var html = '<table id="ranking-table" class="users-table table striped">';
        html += buildHeader(contest, problems, renderer);
        html += '<tbody>';

        for (var i = 0; i < participations.length; i++) {
            html += buildUserRow(participations[i], problems, firstSolves, contest, renderer);
        }

        html += buildTotalACRow(problems, totalAC, renderer.colspanTotalAC, contest.has_rating);
        html += '</tbody></table>';

        var container = document.getElementById('ranking-container');
        if (container) {
            container.innerHTML = html;
        }
    };

    // ─── Virtual Ranking Engine ──────────────────────────────────────────────

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
            if (format === 'icpc') return scoreICPC(probMap, problems, config, cutoff, duration, frozenSec);
            if (format === 'vnoj') return scoreVNOJ(probMap, problems, config, cutoff, duration, frozenSec);
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

    function fetchReplayData(url, contestKey, callback) {
        var cacheKey = 'replay_' + contestKey;
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

    window.initVirtualRanking = function (rankingData, contestKey) {
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
            fetchReplayData(replayUrl, contestKey, function (data) {
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
                fetchReplayData(replayUrl, contestKey, function (data) {
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
