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
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
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

    function getCsrfToken() {
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    // Returns the base CSS state class for a score.
    function baseStateClass(pts, maxPts) {
        if (!pts) return 'failed-score';
        if (pts === maxPts) return 'full-score';
        return 'partial-score';
    }

    // ─── Rating helpers ───────────────────────────────────────────────────────
    // Mirrors judge/ratings.py

    var RATING_VALUES  = [1200, 1400, 1600, 1900, 2200, 2300, 2400, 2600, 2900];
    var RATING_CLASSES = ['rate-newbie','rate-pupil','rate-specialist','rate-expert',
        'rate-candidate-master','rate-master','rate-international-master',
        'rate-grandmaster','rate-international-grandmaster','rate-legendary-grandmaster'];
    var RATING_NAMES   = ['Newbie','Pupil','Specialist','Expert','Candidate Master',
        'Master','International Master','Grandmaster','International Grandmaster',
        'Legendary Grandmaster'];

    function ratingLevel(r) {
        for (var i = 0; i < RATING_VALUES.length; i++) {
            if (r < RATING_VALUES[i]) return i;
        }
        return RATING_VALUES.length;
    }

    function ratingProgress(r) {
        var lvl = ratingLevel(r);
        if (lvl >= RATING_VALUES.length) return 1.0;
        var prev = lvl === 0 ? 0 : RATING_VALUES[lvl - 1];
        return (r - prev) / (RATING_VALUES[lvl] - prev);
    }

    function ratingHtml(r) {
        if (r === null || r === undefined) return '';
        var lvl = ratingLevel(r);
        var cls = RATING_CLASSES[lvl];
        var name = RATING_NAMES[lvl];
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

    function computeFirstSolvesAndTotalAC(participations, problems) {
        var firstSolves = {};
        var totalAC = {};

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
                    if (p.virtual === 0 && (minTime === null || t < minTime)) {
                        minTime = t;
                        firstSolves[pid] = p.id;
                    }
                }
            }
        }

        return { firstSolves: firstSolves, totalAC: totalAC };
    }

    // ─── Format renderers ─────────────────────────────────────────────────────
    // Each renderer provides:
    //   renderProblemCell(entry, problem, participationId, firstSolves, meta) → HTML string for one <td>
    //   renderResultCell(participation, meta) → HTML string for one or more <td>s
    //   extraHeaderCols(meta) → HTML string for extra <th>s after the Points column (before problem columns)
    //   colspanTotalAC → integer colspan for the "Total AC" label cell

    // meta = { contest, urlTemplates, urls }
    function makeSubmissionUrl(meta, username, problemCode) {
        return meta.contest.url_templates.problem_submissions
            .replace('__USERNAME__', username)
            .replace('__PROBLEM__', problemCode);
    }

    function makeAllSubmissionsUrl(meta, username) {
        return meta.contest.url_templates.all_submissions
            .replace('__USERNAME__', username);
    }

    // ── Default ──────────────────────────────────────────────────────────────
    var defaultRenderer = {
        extraHeaderCols: function () { return ''; },
        colspanTotalAC: 3,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);
            var state = (meta.pretest ? 'pretest-' : '') +
                        (isFirst ? 'first-solve ' : '') +
                        baseStateClass(entry.points, problem.points);
            return '<td class="' + state + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) +
                '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                '</a></td>';
        },

        renderResultCell: function (participation, meta) {
            var url = makeAllSubmissionsUrl(meta, participation.user.username);
            return '<td class="user-points">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(participation.score, meta.contest.points_precision)) +
                '<div class="solving-time">' + escapeHtml(fmtTime(participation.cumtime)) + '</div>' +
                '</a></td>';
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
            var isFrozen = !!entry.is_frozen;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);

            var triesText = tries + ' ' + (tries === 1 ? 'try' : 'tries');
            var state = (isFrozen ? 'pending ' : '') +
                        (meta.pretest ? 'pretest-' : '') +
                        (isFirst ? 'first-solve ' : '') +
                        baseStateClass(entry.points, problem.points);

            if (!entry.points) {
                return '<td class="' + state + '">' +
                    '<a href="' + escapeHtml(url) + '">' + escapeHtml(triesText) + '</a></td>';
            }

            return '<td class="' + state + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                '<div class="solving-time-minute">' + Math.floor(entry.time / 60) + '</div>' +
                '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                escapeHtml(triesText) +
                '</a></td>';
        },

        renderResultCell: function (participation, meta) {
            var url = makeAllSubmissionsUrl(meta, participation.user.username);
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
        extraHeaderCols: function () { return ''; },
        colspanTotalAC: 3,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);
            var cfg = meta.contest.format_config || {};
            var showTime = cfg.cumtime || cfg.last_score_altering;
            var state = (meta.pretest ? 'pretest-' : '') +
                        (isFirst ? 'first-solve ' : '') +
                        baseStateClass(entry.points, problem.points);
            return '<td class="' + state + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) +
                '<div class="solving-time">' + (showTime ? escapeHtml(fmtTime(entry.time)) : '') + '</div>' +
                '</a></td>';
        },

        renderResultCell: function (participation, meta) {
            var url = makeAllSubmissionsUrl(meta, participation.user.username);
            var cfg = meta.contest.format_config || {};
            var showTime = cfg.cumtime || cfg.last_score_altering;
            return '<td class="user-points">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(participation.score, meta.contest.points_precision)) +
                '<div class="solving-time">' + (showTime ? escapeHtml(fmtTime(participation.cumtime)) : '') + '</div>' +
                '</a></td>';
        },
    };

    // ── IOI 2016+ (ioi16) ────────────────────────────────────────────────────
    // Inherits legacyIoiRenderer, but format_config only has 'cumtime' (no 'last_score_altering').
    var ioiRenderer = $.extend({}, legacyIoiRenderer);

    // ── AtCoder ───────────────────────────────────────────────────────────────
    var atcoderRenderer = {
        extraHeaderCols: function () { return ''; },
        colspanTotalAC: 3,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);
            var penaltyHtml = entry.penalty
                ? '<small style="color:red"> (' + escapeHtml(fmtPoints(entry.penalty, 0)) + ')</small>'
                : '';
            var state = (meta.pretest ? 'pretest-' : '') +
                        (isFirst ? 'first-solve ' : '') +
                        baseStateClass(entry.points, problem.points);
            return '<td class="' + state + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) +
                penaltyHtml +
                '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                '</a></td>';
        },

        renderResultCell: defaultRenderer.renderResultCell,
    };

    // ── VNOJ ──────────────────────────────────────────────────────────────────
    var vnojRenderer = {
        extraHeaderCols: function () { return ''; },
        colspanTotalAC: 3,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);
            var pending = entry.pending || 0;

            if (!pending) {
                // Normal (non-pending) path
                var penaltyHtml = entry.penalty
                    ? '<small style="color:red"> (' + escapeHtml(fmtPoints(entry.penalty, 0)) + ')</small>'
                    : '';
                var state = (meta.pretest ? 'pretest-' : '') +
                            (isFirst ? 'first-solve ' : '') +
                            baseStateClass(entry.points, problem.points);
                return '<td class="' + state + '">' +
                    '<a href="' + escapeHtml(url) + '">' +
                    '<div>' + escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) + penaltyHtml + '</div>' +
                    '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                    '</a></td>';
            }

            // Pending path: post-freeze submissions hidden
            var state2 = 'pending ' +
                         (meta.pretest ? 'pretest-' : '') +
                         (isFirst ? 'first-solve ' : '') +
                         baseStateClass(entry.points, problem.points);
            var pendingBadge = '<small style="color:black;"> [' + escapeHtml(String(pending)) + ']</small>';

            // Determine displayed points string
            var ptsStr;
            if (!entry.points && !entry.penalty) {
                ptsStr = '?';
            } else {
                ptsStr = escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) + '?';
            }

            return '<td class="' + state2 + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                '<div>' + ptsStr + pendingBadge + '</div>' +
                '<div class="solving-time">?</div>' +
                '</a></td>';
        },

        renderResultCell: defaultRenderer.renderResultCell,
    };

    // ── ECOO ──────────────────────────────────────────────────────────────────
    var ecooRenderer = {
        extraHeaderCols: function () { return ''; },
        colspanTotalAC: 3,

        renderProblemCell: function (entry, problem, participationId, firstSolves, meta) {
            if (!entry) return '<td></td>';
            var pid = String(problem.id);
            var isFirst = firstSolves[pid] === participationId;
            var url = makeSubmissionUrl(meta, meta.username, problem.code);
            var bonusHtml = entry.bonus
                ? '<small> +' + escapeHtml(fmtPoints(entry.bonus, 0)) + '</small>'
                : '';
            var state = (meta.pretest ? 'pretest-' : '') +
                        (isFirst ? 'first-solve ' : '') +
                        baseStateClass(entry.points, problem.points);
            return '<td class="' + state + '">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(entry.points, meta.contest.points_precision)) +
                bonusHtml +
                '<div class="solving-time">' + escapeHtml(fmtTime(entry.time)) + '</div>' +
                '</a></td>';
        },

        renderResultCell: function (participation, meta) {
            var url = makeAllSubmissionsUrl(meta, participation.user.username);
            var cfg = meta.contest.format_config || {};
            var showTime = !!cfg.cumtime;
            return '<td class="user-points">' +
                '<a href="' + escapeHtml(url) + '">' +
                escapeHtml(fmtPoints(participation.score, meta.contest.points_precision)) +
                '<div class="solving-time">' + (showTime ? escapeHtml(fmtTime(participation.cumtime)) : '') + '</div>' +
                '</a></td>';
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
        var csrf = getCsrfToken();

        var html = '<span class="contest-participation-operation">' +
            '<form action="' + escapeHtml(contest.disqualify_url) + '" method="post">' +
            '<input type="hidden" name="csrfmiddlewaretoken" value="' + escapeHtml(csrf) + '">' +
            '<input type="hidden" name="participation" value="' + p.id + '">' +
            '<a href="#" title="' + escapeHtml(disqLabel) + '" class="' + disqClass + '">' +
            '<i class="fa ' + disqIcon + ' fa-fw"></i></a>' +
            '</form>';

        if (contest.can_change_participation) {
            html += '<a href="' + escapeHtml(p.admin_url) + '" title="Admin" class="edit-participation">' +
                '<i class="fa fa-cog fa-fw"></i></a>';
        }
        html += '</span>';
        return html;
    }

    function buildUserRow(participation, problems, firstSolves, contest, renderer) {
        var p = participation;
        var u = p.user;
        var isICPC = contest.format === 'icpc';
        var rank = p.rank;

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
            rankDisplay = escapeHtml(String(rank));
        }
        html += '<td>' + rankDisplay + '</td>';

        // ICPC: extra rank/penalty col is in extraHeaderCols – no extra td per row
        // (ICPC has the penalty in the result cell instead)

        // Username cell
        html += '<td class="user-name"><div>';
        html += '<div style="float:left">';

        // User link
        var userLink = '<span class="' + escapeHtml(u.css_class) + '">' +
            '<a href="' + escapeHtml(u.url) + '" style="display: inline-block;">' +
            escapeHtml(u.display_name) + '</a></span>';

        if (p.virtual > 0) {
            var virtualTitle = p.virtual + ' virtual participation' + (p.virtual > 1 ? 's' : '') + ' of this user';
            userLink += '<sup class="virtual-participation" title="' + escapeHtml(virtualTitle) + '">' +
                '[' + p.virtual + ']</sup>';
        }
        html += userLink;

        // Personal info (full name) – hidden by default
        html += '<div class="personal-info"><span>' + escapeHtml(u.name || '') + '</span></div>';
        html += '</div>';

        // Right float (start time, admin ops, org)
        html += '<div style="float:right">';

        if (!contest.ended) {
            if (!p.participation_ended) {
                html += '<div class="start-time active">Started ' + escapeHtml(moment(p.start).fromNow()) + '</div>';
            } else {
                html += '<div class="start-time">Participation ended.</div>';
            }
        }

        html += buildAdminOps(p, contest);

        html += '<div class="personal-info" style="text-align: right;">';
        if (u.organization) {
            html += '<span class="organization">' +
                '<a href="' + escapeHtml(u.organization.url) + '">' +
                escapeHtml(u.organization.short_name) + '</a></span>';
        }
        html += '</div>';
        html += '</div>';
        html += '</div></td>'; // close user-name td

        // Build meta for renderer
        var meta = {
            contest: contest,
            username: u.username,
            pretest: contest.run_pretests_only,
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

        var renderer = RENDERERS[contest.format] || RENDERERS['default'];
        var result = computeFirstSolvesAndTotalAC(participations, problems);
        var firstSolves = result.firstSolves;
        var totalAC = result.totalAC;

        var isICPC = contest.format === 'icpc';
        var colspan = renderer.colspanTotalAC;

        var html = '<table id="ranking-table" class="users-table table striped">';
        html += buildHeader(contest, problems, renderer);
        html += '<tbody>';

        for (var i = 0; i < participations.length; i++) {
            html += buildUserRow(participations[i], problems, firstSolves, contest, renderer);
        }

        html += buildTotalACRow(problems, totalAC, colspan, contest.has_rating);
        html += '</tbody></table>';

        var container = document.getElementById('ranking-container');
        if (container) {
            container.innerHTML = html;
        }
    };

})(jQuery);
