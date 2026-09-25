(function () {
    'use strict';

    function initFeedbackModal() {
        const modal = document.getElementById('utc-feedback-modal');
        const form = document.getElementById('utc-feedback-form');
        if (!modal || !form) return;

        const dialog = modal.querySelector('.utc-feedback-dialog');
        const success = modal.querySelector('.utc-feedback-success');
        const successLink = modal.querySelector('.utc-feedback-ticket-link');
        const errorBox = modal.querySelector('.utc-feedback-error');
        const submitButton = modal.querySelector('.utc-feedback-submit');
        const kindInput = form.elements.kind;
        const issueUrlInput = form.elements.issue_url;
        const pageTitleInput = form.elements.page_title;
        const userAgentInput = form.elements.user_agent;
        const viewportInput = form.elements.viewport;
        const stepsInput = form.elements.steps;
        const descriptionLabel = document.getElementById('utc-feedback-description-label');
        const descriptionInput = form.elements.description;
        const reportFields = modal.querySelector('.utc-feedback-report-fields');
        const kindButtons = Array.from(modal.querySelectorAll('[data-feedback-kind]'));
        let previouslyFocused = null;

        function setKind(kind) {
            const isReport = kind === 'report';
            kindInput.value = kind;
            reportFields.hidden = !isReport;
            stepsInput.required = isReport;
            descriptionLabel.textContent = isReport ? 'Chuyện gì đã xảy ra?' : 'Bạn muốn đề xuất điều gì?';
            descriptionInput.placeholder = isReport ? 'Mô tả lỗi bạn gặp phải.' : 'Mô tả ý tưởng hoặc đề xuất của bạn.';

            kindButtons.forEach(function (button) {
                const active = button.dataset.feedbackKind === kind;
                button.classList.toggle('is-active', active);
                button.setAttribute('aria-selected', active ? 'true' : 'false');
            });
        }

        function openModal(event) {
            if (event) event.preventDefault();
            previouslyFocused = document.activeElement;
            form.reset();
            form.hidden = false;
            success.hidden = true;
            errorBox.hidden = true;
            submitButton.disabled = false;
            submitButton.textContent = 'Gửi phản hồi';
            issueUrlInput.value = window.location.href;
            pageTitleInput.value = document.title;
            userAgentInput.value = navigator.userAgent;
            viewportInput.value = window.innerWidth + 'x' + window.innerHeight;
            setKind('report');
            modal.classList.add('is-open');
            modal.setAttribute('aria-hidden', 'false');
            document.documentElement.classList.add('utc-modal-open');
            window.setTimeout(function () { form.elements.title.focus(); }, 30);
        }

        function closeModal() {
            modal.classList.remove('is-open');
            modal.setAttribute('aria-hidden', 'true');
            document.documentElement.classList.remove('utc-modal-open');
            if (previouslyFocused) previouslyFocused.focus();
        }

        function showErrors(payload) {
            const messages = [];
            if (payload.error) messages.push(payload.error);
            if (payload.errors) {
                Object.keys(payload.errors).forEach(function (field) {
                    payload.errors[field].forEach(function (message) { messages.push(message); });
                });
            }
            errorBox.textContent = messages.join(' ') || 'Không thể gửi phản hồi. Vui lòng thử lại.';
            errorBox.hidden = false;
        }

        document.querySelectorAll('.utc-feedback-open').forEach(function (button) {
            button.addEventListener('click', openModal);
        });
        modal.querySelectorAll('[data-feedback-close]').forEach(function (button) {
            button.addEventListener('click', closeModal);
        });
        kindButtons.forEach(function (button) {
            button.addEventListener('click', function () { setKind(button.dataset.feedbackKind); });
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (!form.reportValidity()) return;
            errorBox.hidden = true;
            submitButton.disabled = true;
            submitButton.textContent = 'Đang gửi...';

            fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
            }).then(function (response) {
                return response.json().then(function (payload) {
                    return {ok: response.ok, payload: payload};
                });
            }).then(function (result) {
                if (!result.ok || !result.payload.ok) {
                    showErrors(result.payload);
                    return;
                }
                successLink.href = result.payload.ticket_url;
                successLink.textContent = 'Xem ticket #' + result.payload.ticket_id;
                form.hidden = true;
                success.hidden = false;
                success.querySelector('button').focus();
            }).catch(function () {
                showErrors({error: 'Không thể kết nối tới máy chủ. Vui lòng thử lại.'});
            }).finally(function () {
                submitButton.disabled = false;
                submitButton.textContent = 'Gửi phản hồi';
            });
        });

        dialog.addEventListener('click', function (event) { event.stopPropagation(); });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFeedbackModal);
    } else {
        initFeedbackModal();
    }
})();
