// Basic sidepanel logic
console.log('Jobert Side Panel Script Loaded');

document.addEventListener('DOMContentLoaded', () => {
  const authSection = document.getElementById('auth-section');
  const mainSection = document.getElementById('main-section');
  const connectBtn = document.getElementById('connect-btn');
  const scanBtn = document.getElementById('scan-btn');
  const applyBtn = document.getElementById('apply-btn');
  const resetBtn = document.getElementById('reset-btn');
  const authCodeInput = document.getElementById('auth-code');
  const resultsSection = document.getElementById('results-section');
  const questionsList = document.getElementById('questions-list');
  const statusText = document.getElementById('status-text');

  let currentQuestions = [];
  const BACKEND_URL = 'http://localhost:8000';
  const DEMO_USER_ID = 8687167751;

  // Listen for messages from content scripts (especially from iframes)
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'questions_found') {
        console.log(`Received ${message.questions.length} questions from a frame.`);
        
        // If this frame has more questions than what we currently have, use it.
        // This handles cases where forms are in iframes and the main frame is empty.
        if (message.questions.length > currentQuestions.length) {
            currentQuestions = message.questions;
            displayQuestions(currentQuestions);
            statusText.innerText = `Found ${currentQuestions.length} questions.`;
        }
    }
  });

  // Check if already authenticated
  chrome.storage.local.get(['authToken', 'userId'], (result) => {
    if (result.authToken) {
      showMainSection();
    }
  });

  connectBtn.addEventListener('click', async () => {
    const code = authCodeInput.value.trim();
    if (!code) return;

    try {
      const response = await fetch(`${BACKEND_URL}/extension/auth-verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });

      if (response.ok) {
        const data = await response.json();
        chrome.storage.local.set({ authToken: data.token, userId: data.user_id }, () => {
          showMainSection();
        });
      } else {
        alert("Invalid code. Try 123456 for demo.");
      }
    } catch (err) {
      alert("Connection failed. Is the backend running?");
    }
  });

  resetBtn.addEventListener('click', () => {
    chrome.storage.local.clear(() => {
      window.location.reload();
    });
  });

  scanBtn.addEventListener('click', async () => {
    console.log('Scan button clicked');
    statusText.innerText = 'Scanning...';
    currentQuestions = []; // Reset for new scan
    
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab) {
        statusText.innerText = 'No active tab found.';
        return;
    }

    // Trigger scan in all frames
    chrome.tabs.sendMessage(tab.id, { action: 'scan_form' }, (response) => {
        if (chrome.runtime.lastError) {
            console.error('Runtime error:', chrome.runtime.lastError);
            statusText.innerText = 'Error: Refresh the page.';
        }
    });

    // Set a timeout to check if we found anything after a short delay
    setTimeout(() => {
        if (currentQuestions.length === 0) {
            statusText.innerText = 'No questions found.';
        }
    }, 1000);
  });

  applyBtn.addEventListener('click', async () => {
    statusText.innerText = 'Generating tailored answers...';
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    chrome.storage.local.get(['userId'], async (result) => {
      const userId = result.userId ? parseInt(result.userId) : DEMO_USER_ID;

      try {
        const response = await fetch(`${BACKEND_URL}/generate-answers`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            job_url: tab.url,
            questions: currentQuestions
          })
        });

        if (!response.ok) {
          const errData = await response.json();
          throw new Error(errData.detail || 'Generation failed');
        }
        
        const data = await response.json();

        chrome.tabs.sendMessage(tab.id, { action: 'fill_form', answers: data.answers }, (fillResponse) => {
          if (fillResponse && fillResponse.status === 'success') {
            statusText.innerText = 'Form filled successfully!';
          } else {
            statusText.innerText = 'Warning: Check form fields.';
          }
        });
      } catch (err) {
        statusText.innerText = `Error: ${err.message}`;
      }
    });
  });

  function displayQuestions(questions) {
    questionsList.innerHTML = '';
    resultsSection.classList.remove('hidden');
    
    questions.forEach(q => {
      const item = document.createElement('div');
      item.style.padding = '8px 0';
      item.style.borderBottom = '1px solid #eee';
      item.innerHTML = `
        <div style="font-weight: 600; font-size: 0.9rem;">${q.label}</div>
        <div style="font-size: 0.75rem; color: #888;">Type: ${q.type}</div>
      `;
      questionsList.appendChild(item);
    });
  }

  function showMainSection() {
    authSection.classList.add('hidden');
    mainSection.classList.remove('hidden');
  }
});
