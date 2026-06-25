function ChunkedUploader(file, options) {
  this.file = file;
  this.options = options || {};

  // Read config
  let config = window.CHUNKED_UPLOAD_CONFIG || {};
  this.urls = config.urls || {};
  this.i18n = config.i18n || {};
  this.chunkSize = config.chunkSize || 10 * 1024 * 1024;
  this.maxParallel = config.maxParallel || 3;

  this.totalChunks = Math.ceil(file.size / this.chunkSize);
  this.fileId =
    "chunked_" +
    encodeURIComponent(file.name).replace(/[^a-zA-Z0-9]/g, "") +
    "_" +
    file.size +
    "_" +
    file.lastModified;
  this.csrfToken = $("input[name=csrfmiddlewaretoken]").val();

  this.uploadId = "";
  this.uploadedChunksMap = {};
  this.activeCount = 0;
  this.nextIndex = 0;
  this.cancelled = false;
  this.startTime = 0;
  this.chunkProgress = {};
  this.activeXhrs = {};
  this.retries = {};

  // UI elements
  this.$overlay = null;
}

ChunkedUploader.prototype.start = function () {
  let self = this;

  // Clone overlay template
  let $tmpl = $("#chunked-upload-template");
  if ($tmpl.length === 0) {
    console.error("Chunked upload template not found.");
    return;
  }

  self.$overlay = $tmpl.children().first().clone().appendTo("body");
  self.$overlay.show(); // Ensure it is visible since template wrapper might be display: none
  self.$overlay.find(".chunked-upload-filename").text(self.file.name);

  self.$overlay.find(".chunked-upload-cancel-btn").click(() => {
    self.cancel();
  });

  self.startTime = Date.now();
  self.initSession();
};

ChunkedUploader.prototype.cancel = function () {
  let self = this;
  self.cancelled = true;
  for (let idx in self.activeXhrs) {
    if (self.activeXhrs[idx]) {
      try {
        self.activeXhrs[idx].abort();
      } catch (e) {}
    }
  }
  if (self.$overlay) {
    self.$overlay.fadeOut(300, () => {
      $(this).remove();
    });
  }
  if (self.uploadId && self.urls.cancel) {
    let formData = new FormData();
    formData.append("upload_id", self.uploadId);
    let xhr = new XMLHttpRequest();
    xhr.open("POST", self.urls.cancel, true);
    xhr.setRequestHeader("X-CSRFToken", self.csrfToken);
    xhr.send(formData);
  }
  if (self.options.onError) {
    self.options.onError(self.i18n.userCancelled || "Upload cancelled by user.");
  }
};

ChunkedUploader.prototype.handleError = function (msg) {
  let self = this;
  if (self.cancelled) return;
  self.cancel();
  if (self.options.onError) {
    self.options.onError(msg);
  }
};

ChunkedUploader.prototype.updateProgress = function () {
  let self = this;
  let loadedBytes = 0;

  for (let idx = 0; idx < self.totalChunks; idx++) {
    if (self.uploadedChunksMap[idx]) {
      let size =
        idx === self.totalChunks - 1
          ? self.file.size - (self.totalChunks - 1) * self.chunkSize
          : self.chunkSize;
      loadedBytes += size;
    }
  }

  for (let idx in self.chunkProgress) {
    let idxInt = parseInt(idx);
    if (!self.uploadedChunksMap[idxInt]) {
      loadedBytes += self.chunkProgress[idx];
    }
  }

  if (loadedBytes > self.file.size) loadedBytes = self.file.size;

  let percent = Math.floor((loadedBytes / self.file.size) * 100);
  self.$overlay.find(".chunked-upload-progress-fill").css("width", percent + "%");
  self.$overlay.find(".chunked-upload-percentage").text(percent + "%");

  let now = Date.now();
  let elapsedSec = (now - self.startTime) / 1000;
  if (elapsedSec > 0.5) {
    let speed = loadedBytes / elapsedSec;
    let speedText = "";
    if (speed > 1024 * 1024) {
      speedText = (speed / (1024 * 1024)).toFixed(2) + " MB/s";
    } else if (speed > 1024) {
      speedText = (speed / 1024).toFixed(1) + " KB/s";
    } else {
      speedText = speed.toFixed(0) + " B/s";
    }
    self.$overlay.find(".chunked-upload-speed").text(speedText);

    let remainingBytes = self.file.size - loadedBytes;
    let eta = Math.ceil(remainingBytes / speed);
    let etaText = "";
    if (eta > 3600) {
      etaText = Math.floor(eta / 3600) + "h " + Math.floor((eta % 3600) / 60) + "m remaining";
    } else if (eta > 60) {
      etaText = Math.floor(eta / 60) + "m " + (eta % 60) + "s remaining";
    } else {
      etaText = eta + "s remaining";
    }
    self.$overlay.find(".chunked-upload-eta").text(etaText);
  }
};

ChunkedUploader.prototype.initSession = function () {
  let self = this;
  $.ajax({
    url: self.urls.init,
    method: "POST",
    contentType: "application/json",
    headers: { "X-CSRFToken": self.csrfToken },
    data: JSON.stringify({
      filename: self.file.name,
      file_size: self.file.size,
      chunk_size: self.chunkSize,
      total_chunks: self.totalChunks,
      file_id: self.fileId,
    }),
    success: function (res) {
      self.uploadId = res.upload_id;
      let chunks = res.uploaded_chunks || [];
      chunks.forEach(function (idx) {
        self.uploadedChunksMap[idx] = true;
      });
      let uploadedCount = Object.keys(self.uploadedChunksMap).length;

      if (uploadedCount > 0) {
        let resumingMsg = (
          self.i18n.resuming || "Resuming upload: {uploaded}/{total} chunks already uploaded."
        )
          .replace("{uploaded}", uploadedCount)
          .replace("{total}", self.totalChunks);
        self.$overlay.find(".chunked-upload-status").text(resumingMsg);
      } else {
        self.$overlay
          .find(".chunked-upload-status")
          .text(self.i18n.starting || "Starting upload...");
      }

      self.updateProgress();

      // Start upload workers
      for (let i = 0; i < Math.min(self.maxParallel, self.totalChunks); i++) {
        self.uploadWorker();
      }
    },
    error: function (xhr) {
      let errText = xhr.responseJSON
        ? xhr.responseJSON.error
        : self.i18n.initError || "Failed to initialize session";
      self.handleError(errText);
    },
  });
};

ChunkedUploader.prototype.uploadWorker = function () {
  let self = this;
  if (self.cancelled) return;

  let uploadedCount = Object.keys(self.uploadedChunksMap).length;
  if (uploadedCount === self.totalChunks) {
    self.completeSession();
    return;
  }

  while (
    self.nextIndex < self.totalChunks &&
    (self.uploadedChunksMap[self.nextIndex] || self.activeXhrs[self.nextIndex])
  ) {
    self.nextIndex++;
  }

  if (self.nextIndex >= self.totalChunks) {
    return;
  }

  let currentIndex = self.nextIndex;
  self.nextIndex++;

  self.uploadChunk(currentIndex);
};

ChunkedUploader.prototype.uploadChunk = function (index) {
  let self = this;
  self.activeCount++;
  let start = index * self.chunkSize;
  let end = Math.min(start + self.chunkSize, self.file.size);
  let slice = self.file.slice(start, end);

  let formData = new FormData();
  formData.append("upload_id", self.uploadId);
  formData.append("chunk_index", index);
  formData.append("file", slice);

  let xhr = new XMLHttpRequest();
  self.activeXhrs[index] = xhr;

  xhr.open("POST", self.urls.chunk);
  xhr.setRequestHeader("X-CSRFToken", self.csrfToken);

  xhr.upload.onprogress = function (event) {
    if (event.lengthComputable) {
      self.chunkProgress[index] = event.loaded;
      self.updateProgress();
    }
  };

  xhr.onload = () => {
    if (xhr.status === 200) {
      try {
        let res = JSON.parse(xhr.responseText);
        if (res.status === "ok") {
          self.uploadedChunksMap[index] = true;
          delete self.activeXhrs[index];
          delete self.chunkProgress[index];
          self.activeCount--;

          let uploadedCount = Object.keys(self.uploadedChunksMap).length;
          let progressMsg = (self.i18n.uploadedChunk || "Uploaded chunk {current}/{total}")
            .replace("{current}", uploadedCount)
            .replace("{total}", self.totalChunks);
          self.$overlay.find(".chunked-upload-status").text(progressMsg);
          self.updateProgress();

          self.uploadWorker();
        } else {
          self.retryOrError(
            index,
            res.error || self.i18n.chunkUploadError || "Server error uploading chunk",
          );
        }
      } catch (e) {
        self.retryOrError(index, self.i18n.parsingError || "Response parsing error");
      }
    } else {
      let statusErrorMsg = (self.i18n.statusCodeError || "Status code {status}").replace(
        "{status}",
        xhr.status,
      );
      self.retryOrError(index, statusErrorMsg);
    }
  };

  xhr.onerror = () => {
    self.retryOrError(index, self.i18n.networkError || "Network error");
  };

  xhr.send(formData);
};

ChunkedUploader.prototype.retryOrError = function (index, errText) {
  let self = this;
  delete self.activeXhrs[index];
  delete self.chunkProgress[index];
  self.activeCount--;

  let attempt = self.retries[index] || 0;
  if (attempt < 3) {
    self.retries[index] = attempt + 1;
    let retryMsg = (self.i18n.retryingChunk || "Retrying chunk {index} (attempt {attempt})...")
      .replace("{index}", index)
      .replace("{attempt}", self.retries[index]);
    self.$overlay.find(".chunked-upload-status").text(retryMsg);
    setTimeout(() => {
      self.uploadWorker();
    }, 1000 * self.retries[index]);
  } else {
    self.handleError("Failed to upload chunk " + index + " due to: " + errText);
  }
};

ChunkedUploader.prototype.completeSession = function (attempt) {
  let self = this;
  attempt = attempt || 0;
  self.$overlay.find(".chunked-upload-status").text(self.i18n.completing || "Completing upload...");

  let formData = new FormData();
  formData.append("upload_id", self.uploadId);

  let xhr = new XMLHttpRequest();
  xhr.open("POST", self.urls.complete);
  xhr.setRequestHeader("X-CSRFToken", self.csrfToken);
  xhr.onload = () => {
    if (xhr.status === 200) {
      try {
        let res = JSON.parse(xhr.responseText);
        if (res.status === "completed") {
          self.$overlay.fadeOut(300, () => {
            $(this).remove();
          });
          if (self.options.onSuccess) {
            self.options.onSuccess(res.upload_id);
          }
        } else {
          self.retryCompleteOrError(
            attempt,
            res.error || self.i18n.completeError || "Failed to complete session",
          );
        }
      } catch (e) {
        self.retryCompleteOrError(
          attempt,
          self.i18n.parseCompleteError || "Error parsing completion response",
        );
      }
    } else {
      let completeStatusErrorMsg = (
        self.i18n.completeStatusError || "Completion status {status}"
      ).replace("{status}", xhr.status);
      self.retryCompleteOrError(attempt, completeStatusErrorMsg);
    }
  };
  xhr.onerror = () => {
    self.retryCompleteOrError(
      attempt,
      self.i18n.networkCompleteError || "Network error completing session",
    );
  };
  xhr.send(formData);
};

ChunkedUploader.prototype.retryCompleteOrError = function (attempt, errText) {
  let self = this;
  if (attempt < 3) {
    let nextAttempt = attempt + 1;
    let retryMsg = (
      self.i18n.retryingComplete || "Retrying completion (attempt {attempt})..."
    ).replace("{attempt}", nextAttempt);
    self.$overlay.find(".chunked-upload-status").text(retryMsg);
    setTimeout(() => {
      self.completeSession(nextAttempt);
    }, 1000 * nextAttempt);
  } else {
    self.handleError("Failed to complete session due to: " + errText);
  }
};
