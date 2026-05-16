// Script to extract review data from Sea of Tranquility review page

function extractReviewData() {
  const bodyText = document.body.innerText;
  
  // Find the title - it's in a specific format on the page
  // Look for pattern: Title text followed by review body, then "Added:", "Reviewer:", "Score:"
  let title = '';
  const lines = bodyText.split('\n');
  
  // Find the line that looks like a review title (has format "Artist: Album" or just "Album")
  // It's the first meaningful text block after the nav elements
  let inReviewArea = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    // Skip nav elements
    if (line === 'Home' || line === 'REVIEWS' || line === 'Search' || line === 'All' || 
        line === 'Articles' || line === 'Main Menu' || line === 'Topics' || line === 'Sections' ||
        line === 'Visit Our Friends At:' || line === 'May 16, 2026' || line === 'Go!' ||
        line.startsWith('·')) continue;
    if (line.length > 3 && line.length < 200) {
      title = line;
      break;
    }
  }
  
  // Extract metadata
  const addedMatch = bodyText.match(/Added:\s*(.+?)(?:\n|$)/);
  const reviewerMatch = bodyText.match(/Reviewer:\s*(.+?)(?:\n|$)/);
  const scoreMatch = bodyText.match(/Score:\s*(\S+)(?:\n|$)/);
  
  const pubDate = addedMatch ? addedMatch[1].trim() : '';
  const reviewer = reviewerMatch ? reviewerMatch[1].trim() : '';
  const score = scoreMatch && scoreMatch[1] !== 'Score:' ? scoreMatch[1].trim() : '';
  
  // Body is between title and "Added:"
  let body = '';
  const addedIdx = bodyText.indexOf('Added:');
  if (addedIdx > 0) {
    body = bodyText.substring(0, addedIdx);
    const titleIdx = body.lastIndexOf(title);
    if (titleIdx >= 0) {
      body = body.substring(titleIdx + title.length);
    }
    // Remove track listing
    const trackIdx = body.indexOf('Track Listing');
    if (trackIdx > 0) body = body.substring(0, trackIdx);
    body = body.replace(/\s+/g, ' ').trim();
  }
  
  // Excerpt is first 500 chars of body
  const excerpt = body.length > 500 ? body.substring(0, 500) + '...' : body;
  
  // Parse artist/album from title
  let artist = '', album = '';
  if (title.includes(':')) {
    const parts = title.split(':');
    artist = parts[0].trim();
    album = parts.slice(1).join(':').trim();
  } else {
    album = title;
  }
  
  return {
    title,
    artist,
    album,
    pubDate,
    reviewer,
    score,
    body,
    excerpt,
    url: window.location.href
  };
}

return JSON.stringify(extractReviewData());
