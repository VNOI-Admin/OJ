/**
 * UTCOJ - Google Form generator for "Bao loi & Gop y".
 *
 * CACH SU DUNG
 * 1. Truy cap https://script.google.com/ va tao New project.
 * 2. Xoa code mac dinh trong Code.gs.
 * 3. Dan toan bo noi dung file nay vao Code.gs.
 * 4. Chon ham createUtcojFeedbackForm, bam Run va cap quyen.
 * 5. Mo Execution log de lay link Form, Sheet va file config.
 *
 * Script chi can chay MOT LAN. Moi lan chay lai se tao mot bo Form/Sheet moi.
 */

function createUtcojFeedbackForm() {
  var folder = DriveApp.createFolder('UTCOJ - Bao loi va Gop y');
  var form = FormApp.create('UTCOJ - Bao lỗi & Góp ý');

  form
    .setDescription(
      'Kênh tiếp nhận báo lỗi và góp ý chính thức của UTCOJ - Khoa Công nghệ Thông tin, ' +
      'Trường Đại học Giao thông Vận tải. Thông tin liên lạc và dữ liệu kỹ thuật không bắt buộc.'
    )
    .setConfirmationMessage('Cảm ơn bạn! Phản hồi đã được gửi tới đội ngũ UTCOJ.')
    .setCollectEmail(false)
    .setLimitOneResponsePerUser(false)
    .setProgressBar(true)
    .setShowLinkToRespondAgain(true)
    .setAcceptingResponses(true);

  form.addSectionHeaderItem()
    .setTitle('Nội dung phản hồi')
    .setHelpText('Các trường có dấu * là bắt buộc.');

  var kind = form.addMultipleChoiceItem()
    .setTitle('Loại phản hồi')
    .setChoiceValues(['Báo lỗi', 'Góp ý'])
    .setRequired(true);

  var title = form.addTextItem()
    .setTitle('Tiêu đề')
    .setHelpText('Ví dụ: Nút nộp bài không bấm được')
    .setRequired(true);

  var description = form.addParagraphTextItem()
    .setTitle('Mô tả chi tiết')
    .setHelpText('Mô tả lỗi bạn gặp phải hoặc ý tưởng bạn muốn đề xuất.')
    .setRequired(true);

  form.addSectionHeaderItem()
    .setTitle('Thông tin dành cho báo lỗi')
    .setHelpText('Có thể bỏ trống hai trường dưới đây nếu bạn chỉ gửi góp ý.');

  var steps = form.addParagraphTextItem()
    .setTitle('Các bước tái hiện')
    .setHelpText('Ví dụ: 1. Mở trang... 2. Bấm vào... 3. Lỗi xuất hiện.')
    .setRequired(false);

  var impact = form.addMultipleChoiceItem()
    .setTitle('Mức độ ảnh hưởng')
    .setChoiceValues(['Không làm tiếp được', 'Có cách xử lý tạm', 'Chỉ hơi khó chịu'])
    .setRequired(false);

  form.addSectionHeaderItem()
    .setTitle('Thông tin liên lạc')
    .setHelpText('Không bắt buộc. Chỉ dùng khi đội ngũ UTCOJ cần làm rõ phản hồi.');

  var contact = form.addTextItem()
    .setTitle('SĐT, email, Discord hoặc kênh liên lạc khác')
    .setRequired(false);

  var utcojUser = form.addTextItem()
    .setTitle('Tài khoản UTCOJ')
    .setHelpText('Trường này sẽ được website tự điền khi tích hợp.')
    .setRequired(false);

  form.addSectionHeaderItem()
    .setTitle('Thông tin trang và kỹ thuật')
    .setHelpText('Các trường này sẽ được website UTCOJ tự điền nếu người dùng đồng ý gửi kèm.');

  var issueUrl = form.addTextItem()
    .setTitle('Địa chỉ trang đang mở')
    .setValidation(FormApp.createTextValidation().requireTextIsUrl().build())
    .setRequired(true);

  var pageTitle = form.addTextItem()
    .setTitle('Tên trang')
    .setRequired(false);

  var includeTechnical = form.addMultipleChoiceItem()
    .setTitle('Người dùng đồng ý gửi thông tin kỹ thuật')
    .setChoiceValues(['Có', 'Không'])
    .setRequired(true);

  var viewport = form.addTextItem()
    .setTitle('Kích thước cửa sổ trình duyệt')
    .setHelpText('Ví dụ: 1920x1080')
    .setRequired(false);

  var userAgent = form.addParagraphTextItem()
    .setTitle('User agent')
    .setRequired(false);

  var ticketId = form.addTextItem()
    .setTitle('Mã ticket UTCOJ')
    .setHelpText('Dùng để đối chiếu với ticket lưu trong website.')
    .setRequired(false);

  var spreadsheet = SpreadsheetApp.create('UTCOJ - Phản hồi từ website');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());

  DriveApp.getFileById(form.getId()).moveTo(folder);
  DriveApp.getFileById(spreadsheet.getId()).moveTo(folder);

  // Tao pre-filled URL bang cac gia tri doc nhat de tim dung entry.xxxxx.
  var samples = {
    kind: 'Báo lỗi',
    title: 'UTCOJ_FIELD_TITLE',
    description: 'UTCOJ_FIELD_DESCRIPTION',
    steps: 'UTCOJ_FIELD_STEPS',
    impact: 'Không làm tiếp được',
    contact: 'UTCOJ_FIELD_CONTACT',
    utcoj_user: 'UTCOJ_FIELD_USER',
    issue_url: 'https://example.com/utcoj-feedback-page',
    page_title: 'UTCOJ_FIELD_PAGE_TITLE',
    include_technical: 'Có',
    viewport: 'UTCOJ_FIELD_VIEWPORT',
    user_agent: 'UTCOJ_FIELD_USER_AGENT',
    ticket_id: 'UTCOJ_FIELD_TICKET_ID'
  };

  var prefilled = form.createResponse()
    .withItemResponse(kind.createResponse(samples.kind))
    .withItemResponse(title.createResponse(samples.title))
    .withItemResponse(description.createResponse(samples.description))
    .withItemResponse(steps.createResponse(samples.steps))
    .withItemResponse(impact.createResponse(samples.impact))
    .withItemResponse(contact.createResponse(samples.contact))
    .withItemResponse(utcojUser.createResponse(samples.utcoj_user))
    .withItemResponse(issueUrl.createResponse(samples.issue_url))
    .withItemResponse(pageTitle.createResponse(samples.page_title))
    .withItemResponse(includeTechnical.createResponse(samples.include_technical))
    .withItemResponse(viewport.createResponse(samples.viewport))
    .withItemResponse(userAgent.createResponse(samples.user_agent))
    .withItemResponse(ticketId.createResponse(samples.ticket_id))
    .toPrefilledUrl();

  var entryIds = extractEntryIds(prefilled, samples);
  var publishedUrl = form.getPublishedUrl();
  var responseUrl = publishedUrl.replace(/\/viewform(?:\?.*)?$/, '/formResponse');

  var config = {
    form_edit_url: form.getEditUrl(),
    form_published_url: publishedUrl,
    form_response_url: responseUrl,
    prefilled_test_url: prefilled,
    spreadsheet_url: spreadsheet.getUrl(),
    entry_ids: entryIds
  };

  var configFile = folder.createFile(
    'UTCOJ-feedback-config.json',
    JSON.stringify(config, null, 2),
    MimeType.PLAIN_TEXT
  );

  console.log('=== UTCOJ FEEDBACK FORM CREATED ===');
  console.log('Folder: ' + folder.getUrl());
  console.log('Edit Form: ' + config.form_edit_url);
  console.log('Published Form: ' + config.form_published_url);
  console.log('Response endpoint: ' + config.form_response_url);
  console.log('Response Sheet: ' + config.spreadsheet_url);
  console.log('Config file: ' + configFile.getUrl());
  console.log('Pre-filled test URL: ' + config.prefilled_test_url);
  console.log('Entry IDs: ' + JSON.stringify(config.entry_ids, null, 2));

  return config;
}

function extractEntryIds(prefilledUrl, samples) {
  var query = prefilledUrl.split('?')[1] || '';
  var valueToField = {};
  var result = {};

  Object.keys(samples).forEach(function (field) {
    valueToField[String(samples[field])] = field;
  });

  query.split('&').forEach(function (pair) {
    if (!pair) return;
    var parts = pair.split('=');
    var key = decodeURIComponent(parts.shift());
    var value = decodeURIComponent(parts.join('=').replace(/\+/g, ' '));
    if (key.indexOf('entry.') === 0 && valueToField[value]) {
      result[valueToField[value]] = key;
    }
  });

  return result;
}
