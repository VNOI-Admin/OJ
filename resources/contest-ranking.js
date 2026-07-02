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
        var url = makeSubmissionUrl(meta, problem.order);

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
            var url = makeSubmissionUrl(meta, problem.order);

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
            var url = makeSubmissionUrl(meta, problem.order);
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
            if (prob.code) {
                html += '<div class="problem-code" style="display:none;">' + escapeHtml(prob.code) + '</div>';
            }
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

})(jQuery);
