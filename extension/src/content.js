// Content script for scanning the page and injecting answers
console.log('Jobert Content Script Loaded');

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Content script received message:', request.action);
  
  if (request.action === 'scan_form') {
    const questions = scanForQuestions();
    console.log(`Scanned ${questions.length} questions in this frame.`);
    
    // Send findings back as a separate message to ensure the sidepanel receives all frames
    if (questions.length > 0) {
        chrome.runtime.sendMessage({ action: 'questions_found', questions });
    }
    
    sendResponse({ questions }); // Also respond to the original message
    return false;
  } else if (request.action === 'fill_form') {
    try {
      fillForm(request.answers);
      sendResponse({ status: 'success' });
    } catch (error) {
      console.error('Fill form error:', error);
      sendResponse({ status: 'error', message: error.message });
    }
    return false;
  }
});

function scanForQuestions() {
  const extractedQuestions = [];
  const inputs = document.querySelectorAll('input, textarea, select');

  inputs.forEach(input => {
    // Skip hidden, buttons, file inputs
    if (['hidden', 'submit', 'button', 'file', 'reset'].includes(input.type)) return;
    
    // Filter out common cookie/tracking/consents that aren't part of the job form
    const id = input.id || '';
    const name = input.name || '';
    if (id.includes('wccSwitch') || id.includes('cookie') || name.includes('tracking')) return;

    const label = findLabel(input);
    if (label) {
      extractedQuestions.push({
        id: input.id || input.name || `field-${Math.random().toString(36).substr(2, 5)}`,
        label: label.innerText.trim().replace(/\s+/g, ' '),
        type: input.type || input.tagName.toLowerCase(),
        placeholder: input.placeholder || ''
      });
    }
  });

  return extractedQuestions;
}

function findLabel(el) {
  // 1. Standard <label for="ID">
  if (el.id) {
    const label = document.querySelector(`label[for="${el.id}"]`);
    if (label) return label;
  }
  
  // 2. Parent <label> wrapper
  const parentLabel = el.closest('label');
  if (parentLabel) return parentLabel;

  // 3. Aria-labelledby
  const ariaLabelledBy = el.getAttribute('aria-labelledby');
  if (ariaLabelledBy) {
    const label = document.getElementById(ariaLabelledBy);
    if (label) return label;
  }

  // 4. Aria-label
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel) return { innerText: ariaLabel };

  // 5. Closest preceding element with "label" class or tagName
  let prev = el.previousElementSibling;
  while (prev) {
    if (prev.tagName === 'LABEL' || prev.classList.contains('label') || prev.tagName.startsWith('H')) {
      return prev;
    }
    prev = prev.previousElementSibling;
  }
  
  // 6. Parent sibling search
  let parent = el.parentElement;
  if (parent) {
    let parentPrev = parent.previousElementSibling;
    if (parentPrev && (parentPrev.tagName === 'LABEL' || parentPrev.querySelector('label') || parentPrev.classList.contains('label'))) {
        return parentPrev.querySelector('label') || parentPrev;
    }
  }

  // 7. Placeholder as absolute fallback
  if (el.placeholder) return { innerText: el.placeholder };

  return null;
}

function fillForm(answers) {
  for (const [id, value] of Object.entries(answers)) {
    let el = document.getElementById(id) || document.getElementsByName(id)[0];
    
    if (el) {
      if (el.tagName === 'INPUT' && (el.type === 'file' || el.type === 'button' || el.type === 'submit')) {
        continue;
      }
      
      el.focus();
      el.value = '';
      el.value = value;

      // Trigger all possible events for SPA compatibility
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new Event('blur', { bubbles: true }));
    }
  }
}
