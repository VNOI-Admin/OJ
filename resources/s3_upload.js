function putWithProgress(url, contentType, file, onProgress) {
    return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open('PUT', url);
        xhr.setRequestHeader('Content-Type', contentType);
        xhr.upload.onprogress = function (e) {
            if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
        xhr.onload = function () {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else reject(new Error('S3 error ' + xhr.status));
        };
        xhr.onerror = function () { reject(new Error('S3 network error')); };
        xhr.send(file);
    });
}

$(function () {
    document.querySelectorAll('.s3-upload-widget').forEach(function (widget) {
        var picker = widget.querySelector('input[type=file]');
        var hidden = widget.querySelector('input[type=hidden]');
        var status = widget.querySelector('.s3-upload-status');
        var progress = widget.querySelector('.s3-upload-progress');
        var threshold = parseInt(widget.dataset.fallbackThreshold || '0');

        picker.addEventListener('change', async function () {
            var file = this.files[0];
            if (!file) return;

            // Below threshold: let the native file input submit as a regular upload.
            if (threshold > 0 && file.size <= threshold) {
                hidden.value = '';
                status.textContent = '';
                return;
            }

            var maxSize = parseInt(picker.dataset.maxSize);
            if (file.size > maxSize) {
                status.textContent = 'File too large (max ' + Math.round(maxSize / 1048576) + ' MB)';
                return;
            }
            status.textContent = 'Uploading…';
            hidden.value = '';
            progress.value = 0;
            progress.style.display = '';
            try {
                var resp = await fetch(widget.dataset.presignUrl, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': $.cookie('csrftoken')},
                    body: JSON.stringify({token: widget.dataset.token, filename: file.name, size: file.size,
                                         content_type: file.type || 'application/octet-stream'}),
                });
                var data = await resp.json();
                if (data.error) throw new Error(data.error);
                await putWithProgress(data.url, data.content_type, file, function (fraction) {
                    progress.value = Math.round(fraction * 100);
                    status.textContent = 'Uploading… ' + progress.value + '%';
                });
                hidden.value = data.file_url;
                picker.disabled = true;  // ponytail: prevents double-submit of the file body
                status.textContent = '✓ ' + file.name;
            } catch (e) {
                // S3 failed: fall back to regular upload via the file input.
                hidden.value = '';
                picker.disabled = false;
                status.textContent = 'Direct upload failed, uploading via server…';
            } finally {
                progress.style.display = 'none';
            }
        });
    });
});
