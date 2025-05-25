// filename: app.js

/*
App.js handles the frontend logic for uploading PDF files to a server endpoint.
It validates the input, shows a loading spinner, sends the files via a POST request,
and displays the extracted JSON or error response from the backend.
*/

// Function to safely escape HTML characters to prevent XSS
function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Main function to handle PDF upload and response display
async function uploadPDF() {
  const input = document.getElementById('fileInput');
  const output = document.getElementById('jsonOutput');
  const submitBtn = document.querySelector('button');

  // Show loading spinner and disable the submit button during processing
  output.innerHTML = `
    <div class="spinner-container">
      <div class="spinner"></div>
      <p>Processing PDF...</p>
    </div>
  `;
  submitBtn.disabled = true;

  try {
    const files = input.files;

    // Check if user selected at least one file
    if (!files.length) {
      throw new Error("Please select at least one PDF file.");
    }

    // Validate that all files have .pdf extension
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        throw new Error(`${file.name} is not a PDF file.`);
      }
    }

    // Create FormData and append selected PDF files
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }

    // Send files to the server via POST request
    const response = await fetch('/upload', {
      method: 'POST',
      body: formData,
    });

    // Handle server-side errors and fallback if response is not JSON
    if (!response.ok) {
      let errorMessage = "Failed to process PDF";
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorMessage;
      } catch {
        // fallback if response is not JSON
      }
      throw new Error(errorMessage);
    }

    const data = await response.json();

    // Check for success flag in response
    if (!data || !data.success) {
      throw new Error(data.error || "Unexpected error during extraction.");
    }

    // Escape and format JSON response for display
    const escapedJSON = escapeHTML(JSON.stringify(data, null, 2));
    output.innerHTML = `<pre>${escapedJSON}</pre>`;

  } catch (error) {
    // Show error message in the UI and log to console
    output.innerHTML = `<div class="error">Error: ${escapeHTML(error.message)}</div>`;
    console.error('Upload failed:', error);
  } finally {
    // Re-enable submit button after request finishes
    submitBtn.disabled = false;
  }
}
