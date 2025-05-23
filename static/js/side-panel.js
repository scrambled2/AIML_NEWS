/**
 * Side Panel Article Viewer
 * Handles loading article content into the side panel without page reload
 */
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const articleList = document.getElementById('article-list');
    const sidePanel = document.getElementById('side-panel');
    const articleContent = document.getElementById('article-content');
    const loadingIndicator = document.getElementById('loading-indicator');
    const closeButton = document.getElementById('close-panel');
    const sidePanelPlaceholder = document.getElementById('side-panel-placeholder');

    // Mobile detection
    let isMobile = window.innerWidth < 768;

    // State
    let currentArticleId = null;

    // Extract article ID from URL if present
    function getArticleIdFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('article_id');
    }

    // Initialize on page load
    function init() {
        // Check if we have an article ID in the URL
        const articleId = getArticleIdFromUrl();
        if (articleId) {
            loadArticle(articleId);
        }

        // Add event listeners to all article links
        setupArticleLinks();

        // Handle close button
        if (closeButton) {
            closeButton.addEventListener('click', closePanel);
        }

        // Handle window resize
        window.addEventListener('resize', handleResize);
    }

    // Setup event listeners for article links
    function setupArticleLinks() {
        const articleLinks = document.querySelectorAll('.article-link');
        articleLinks.forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const articleId = this.getAttribute('data-article-id');
                loadArticle(articleId);

                // Mark as active
                document.querySelectorAll('.article-card').forEach(card => {
                    card.classList.remove('active-article');
                });
                this.closest('.article-card').classList.add('active-article');

                // Update URL without page reload
                const url = new URL(window.location);
                url.searchParams.set('article_id', articleId);
                window.history.pushState({}, '', url);

                // On mobile, scroll to the panel
                if (isMobile) {
                    sidePanel.scrollIntoView({ behavior: 'smooth' });
                }
            });
        });
    }

    // Load article content via AJAX
    function loadArticle(articleId) {
        if (articleId === currentArticleId) return;

        currentArticleId = articleId;
        showLoading(true);

        // Show the panel and hide placeholder
        if (sidePanel) {
            sidePanel.classList.remove('d-none');
        }
        if (sidePanelPlaceholder) {
            sidePanelPlaceholder.classList.add('d-none');
        }

        // Fetch the article data
        fetch(`/api/article/${articleId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                renderArticle(data);
                showLoading(false);
            })
            .catch(error => {
                console.error('Error fetching article:', error);
                articleContent.innerHTML = `
                    <div class="alert alert-danger">
                        Error loading article: ${error.message}
                    </div>
                `;
                showLoading(false);
            });
    }

    function renderArticle(data) {
        const article = data.article;
        const keywords = data.keywords || [];
        const arxivInfo = data.arxiv_info || {};

        let keywordsHtml = '';
        if (keywords.length > 0) {
            keywordsHtml = `
                <div class="mb-4">
                    <h6>Keywords:</h6>
                    <div>
                        ${keywords.map(keyword =>
                            `<a href="/?keyword=${encodeURIComponent(keyword)}"
                                class="badge bg-secondary text-decoration-none me-1">${keyword}</a>`
                        ).join('')}
                    </div>
                </div>
            `;
        }

        let summaryHtml = '';
        if (article.summary) {
            summaryHtml = `
                <div class="mb-4">
                    <h4>Summary</h4>
                    <div class="p-3 bg-light rounded">
                        <p>${article.summary}</p>
                    </div>
                    ${article.llm_model_used ?
                        `<small class="text-muted">Generated using ${article.llm_model_used} on
                        ${article.llm_processed_date_formatted}</small>` : ''}
                </div>
            `;
        }

        // ArXiv Section - This is the new part
        let arxivSectionHtml = '';
        if (arxivInfo.is_arxiv) {
            const statusBadges = {
                'not_applicable': 'secondary',
                'pending': 'warning',
                'extracted': 'success',
                'failed': 'danger',
                'unavailable': 'secondary'
            };

            const deepSummaryBadges = {
                'not_requested': 'secondary',
                'pending': 'warning',
                'completed': 'success',
                'failed': 'danger'
            };

            let fullContentSection = '';
            if (arxivInfo.has_full_content && article.full_content) {
                // Detect if this is full paper content vs just abstract
                const isFullPaper = article.full_content.length > 2000 &&
                    (article.full_content.toLowerCase().includes('introduction') ||
                     article.full_content.toLowerCase().includes('methodology') ||
                     article.full_content.toLowerCase().includes('results'));

                const contentLabel = isFullPaper ? 'Full Paper Content' : 'ArXiv Content';
                const maxHeight = isFullPaper ? '400px' : '300px';

                fullContentSection = `
                    <div class="mt-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6>${contentLabel}</h6>
                            <div>
                                ${isFullPaper ? '<span class="badge bg-success me-2">Full Paper</span>' : '<span class="badge bg-info me-2">Abstract+</span>'}
                                <small class="text-muted">Extracted: ${article.full_content_extracted_date_formatted || 'Unknown'}</small>
                            </div>
                        </div>
                        <div class="border p-3 rounded bg-light" style="max-height: ${maxHeight}; overflow-y: auto;">
                            <div style="white-space: pre-wrap; font-family: inherit; font-size: 0.9em; line-height: 1.4;">${article.full_content}</div>
                        </div>
                        ${isFullPaper ? '<small class="text-muted">💡 This appears to be full paper content with multiple sections</small>' : '<small class="text-muted">📄 Enhanced abstract with metadata</small>'}
                    </div>
                `;
            }

            let deepSummarySection = '';
            if (arxivInfo.has_deep_summary && article.deep_summary) {
                // Check if this is a full paper analysis
                const isFullPaperAnalysis = article.deep_summary.includes('*Analysis based on full paper content*');

                deepSummarySection = `
                    <div class="mt-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6>Deep Analysis</h6>
                            <div>
                                ${isFullPaperAnalysis ? '<span class="badge bg-primary me-2">Full Paper Analysis</span>' : '<span class="badge bg-secondary me-2">Abstract Analysis</span>'}
                                <small class="text-muted">Generated: ${article.deep_summary_date_formatted || 'Unknown'}</small>
                            </div>
                        </div>
                        <div class="p-3 border rounded" style="background: linear-gradient(135deg, #e3f2fd, #f3e5f5); max-height: 500px; overflow-y: auto;">
                            <div style="white-space: pre-wrap; line-height: 1.5;">${article.deep_summary}</div>
                        </div>
                        ${isFullPaperAnalysis ? '<small class="text-muted">🧠 Comprehensive analysis based on full paper content</small>' : '<small class="text-muted">📝 Analysis based on abstract and metadata</small>'}
                    </div>
                `;
            }

            let actionButtons = '';
            if (!arxivInfo.has_full_content && ['not_applicable', 'failed', null, undefined].includes(article.full_content_status)) {
                actionButtons += `
                    <button class="btn btn-sm btn-outline-primary me-2" id="extract-arxiv-btn" data-article-id="${article.id}">
                        <i class="fas fa-download"></i> Extract Full Content
                    </button>
                `;
            } else if (article.full_content_status === 'pending') {
                actionButtons += `
                    <button class="btn btn-sm btn-secondary me-2" disabled>
                        <i class="fas fa-spinner fa-spin"></i> Extracting...
                    </button>
                `;
            }

            if (arxivInfo.has_full_content && !arxivInfo.has_deep_summary && article.deep_summary_status !== 'pending') {
                actionButtons += `
                    <button class="btn btn-sm btn-outline-success" id="deep-summary-btn" data-article-id="${article.id}">
                        <i class="fas fa-brain"></i> Generate Deep Analysis
                    </button>
                `;
            }

            arxivSectionHtml = `
                <div class="mb-4" id="arxiv-section">
                    <div class="card border-primary">
                        <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="fas fa-graduation-cap"></i> ArXiv Paper</h6>
                            <span class="badge bg-light text-primary">ID: ${arxivInfo.arxiv_id}</span>
                        </div>
                        <div class="card-body">
                            <div class="row mb-3">
                                <div class="col-6">
                                    <small class="text-muted">Full Content Status:</small><br>
                                    <span class="badge bg-${statusBadges[article.full_content_status] || 'secondary'}">${article.full_content_status || 'unknown'}</span>
                                </div>
                                <div class="col-6">
                                    <small class="text-muted">Deep Analysis Status:</small><br>
                                    <span class="badge bg-${deepSummaryBadges[article.deep_summary_status] || 'secondary'}">${article.deep_summary_status || 'not_requested'}</span>
                                </div>
                            </div>

                            ${actionButtons ? `<div class="mb-3">${actionButtons}</div>` : ''}

                            ${fullContentSection}
                            ${deepSummarySection}
                        </div>
                    </div>
                </div>
            `;
        }

        let contentHtml = '';
        if (article.raw_content && !arxivInfo.is_arxiv) {
            contentHtml = `
                <div class="mb-4">
                    <h4>Content</h4>
                    <div class="article-content border p-3 rounded" style="max-height: 500px; overflow-y: auto;">
                        ${article.raw_content}
                    </div>
                </div>
            `;
        }

        // Favorites section (existing code)
        let favoritesHtml = `
            <div class="mb-4" id="favorites-section">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6>Favorites</h6>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-danger" id="favorite-btn" data-article-id="${article.id}">
                            <i class="fas fa-heart" id="favorite-icon"></i>
                            <span id="favorite-text">Loading...</span>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary d-none" id="edit-favorite-btn" data-article-id="${article.id}">
                            <i class="fas fa-edit"></i>
                        </button>
                    </div>
                </div>
                <div id="favorite-details" class="d-none">
                    <div class="card bg-light">
                        <div class="card-body p-2">
                            <div id="favorite-notes-display" class="mb-2"></div>
                            <div id="favorite-tags-display"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        articleContent.innerHTML = `
            <div class="d-flex justify-content-between mb-3">
                <span class="badge bg-primary">${article.feed_name}</span>
                <small class="text-muted">Published: ${article.published_date_formatted}</small>
            </div>

            <h1 class="mb-4">${article.title}</h1>

            <div class="mb-4">
                <a href="${article.link}" class="btn btn-primary" target="_blank">View Original Article</a>
                <a href="/article/${article.id}" class="btn btn-secondary">Full Page View</a>
            </div>

            ${arxivSectionHtml}
            ${favoritesHtml}
            ${keywordsHtml}
            ${summaryHtml}
            ${contentHtml}

            <div class="card-footer text-muted mt-4">
                <div class="row">
                    <div class="col">
                        Added to database: ${article.fetched_date_formatted}
                    </div>
                    <div class="col text-end">
                        Status: ${article.processing_status}
                    </div>
                </div>
            </div>
        `;

        // Load favorite status after rendering
        loadFavoriteStatus(article.id);

        // Setup favorite button handlers
        setupFavoriteHandlers(article.id);

        // Setup ArXiv handlers
        setupArxivHandlers(article.id);
    }

    // Toggle loading indicator
    function showLoading(isLoading) {
        if (loadingIndicator) {
            if (isLoading) {
                loadingIndicator.classList.remove('d-none');
                articleContent.classList.add('d-none');
            } else {
                loadingIndicator.classList.add('d-none');
                articleContent.classList.remove('d-none');
            }
        }
    }

    // Close the side panel (mobile only)
    function closePanel() {
        if (sidePanel) {
            if (isMobile) {
                sidePanel.classList.add('d-none');
                if (sidePanelPlaceholder) {
                    sidePanelPlaceholder.classList.remove('d-none');
                }
            } else {
                // On desktop, just clear content but keep panel visible
                if (sidePanelPlaceholder) {
                    sidePanelPlaceholder.classList.remove('d-none');
                }
                if (articleContent) {
                    articleContent.classList.add('d-none');
                }
                if (loadingIndicator) {
                    loadingIndicator.classList.add('d-none');
                }
            }

            // Update URL to remove article_id
            const url = new URL(window.location);
            url.searchParams.delete('article_id');
            window.history.pushState({}, '', url);

            // Clear current article id
            currentArticleId = null;

            // Remove active article highlighting
            document.querySelectorAll('.article-card').forEach(card => {
                card.classList.remove('active-article');
            });
        }
    }

    // Handle window resize
    function handleResize() {
        const wasMobile = isMobile;
        const newIsMobile = window.innerWidth < 768;

        // Update mobile state
        isMobile = newIsMobile;

        // If switching between mobile and desktop, adjust the UI
        if (wasMobile !== newIsMobile) {
            // Refresh the UI based on new size
            if (newIsMobile) {
                // Switched to mobile
                if (sidePanel && !currentArticleId) {
                    sidePanel.classList.add('d-none');
                    if (sidePanelPlaceholder) {
                        sidePanelPlaceholder.classList.remove('d-none');
                    }
                }
            } else {
                // Switched to desktop
                if (sidePanel) {
                    sidePanel.classList.remove('d-none');
                    if (sidePanelPlaceholder) {
                        sidePanelPlaceholder.classList.add('d-none');
                    }
                }
            }
        }
    }

    // Load favorite status for an article
    function loadFavoriteStatus(articleId) {
        fetch(`/api/favorite/${articleId}/status`)
            .then(response => response.json())
            .then(data => {
                const favoriteBtn = document.getElementById('favorite-btn');
                const favoriteIcon = document.getElementById('favorite-icon');
                const favoriteText = document.getElementById('favorite-text');
                const editBtn = document.getElementById('edit-favorite-btn');
                const detailsDiv = document.getElementById('favorite-details');

                if (data.is_favorite) {
                    favoriteBtn.classList.remove('btn-outline-danger');
                    favoriteBtn.classList.add('btn-danger');
                    favoriteIcon.classList.add('text-white');
                    favoriteText.textContent = 'Favorited';
                    editBtn.classList.remove('d-none');

                    // Show favorite details if they exist
                    if (data.notes || data.tags) {
                        displayFavoriteDetails(data.notes, data.tags);
                        detailsDiv.classList.remove('d-none');
                    }
                } else {
                    favoriteBtn.classList.remove('btn-danger');
                    favoriteBtn.classList.add('btn-outline-danger');
                    favoriteIcon.classList.remove('text-white');
                    favoriteText.textContent = 'Add to Favorites';
                    editBtn.classList.add('d-none');
                    detailsDiv.classList.add('d-none');
                }
            })
            .catch(error => {
                console.error('Error loading favorite status:', error);
                document.getElementById('favorite-text').textContent = 'Error';
            });
    }

    // Display favorite details
    function displayFavoriteDetails(notes, tags) {
        const notesDisplay = document.getElementById('favorite-notes-display');
        const tagsDisplay = document.getElementById('favorite-tags-display');

        if (notes) {
            notesDisplay.innerHTML = `<small><strong>Notes:</strong> ${notes}</small>`;
            notesDisplay.classList.remove('d-none');
        } else {
            notesDisplay.classList.add('d-none');
        }

        if (tags) {
            const tagArray = tags.split(',').map(tag => tag.trim()).filter(tag => tag);
            if (tagArray.length > 0) {
                tagsDisplay.innerHTML = `
                    <small><strong>Tags:</strong>
                    ${tagArray.map(tag => `<span class="badge bg-warning text-dark me-1">${tag}</span>`).join('')}
                    </small>
                `;
                tagsDisplay.classList.remove('d-none');
            } else {
                tagsDisplay.classList.add('d-none');
            }
        } else {
            tagsDisplay.classList.add('d-none');
        }
    }

    // Setup favorite button handlers
    function setupFavoriteHandlers(articleId) {
        const favoriteBtn = document.getElementById('favorite-btn');
        const editBtn = document.getElementById('edit-favorite-btn');

        favoriteBtn.addEventListener('click', function() {
            toggleFavorite(articleId);
        });

        editBtn.addEventListener('click', function() {
            openFavoriteModal(articleId);
        });
    }

    // Toggle favorite status
    function toggleFavorite(articleId) {
        const favoriteBtn = document.getElementById('favorite-btn');
        const isCurrentlyFavorited = favoriteBtn.classList.contains('btn-danger');

        if (isCurrentlyFavorited) {
            // Remove from favorites
            if (confirm('Remove this article from favorites?')) {
                fetch(`/api/favorite/${articleId}`, {
                    method: 'DELETE'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        loadFavoriteStatus(articleId); // Refresh the display
                        showToast('Article removed from favorites', 'success');
                    } else {
                        showToast('Error removing favorite: ' + data.error, 'error');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    showToast('Network error occurred', 'error');
                });
            }
        } else {
            // Add to favorites - open modal for notes/tags
            openFavoriteModal(articleId, true);
        }
    }

    // Open favorite modal
    function openFavoriteModal(articleId, isNewFavorite = false) {
        const modal = new bootstrap.Modal(document.getElementById('favoriteModal'));
        const notesInput = document.getElementById('favoriteNotes');
        const tagsInput = document.getElementById('favoriteTags');
        const saveBtn = document.getElementById('saveFavorite');

        // Clear previous handlers
        saveBtn.replaceWith(saveBtn.cloneNode(true));
        const newSaveBtn = document.getElementById('saveFavorite');

        if (isNewFavorite) {
            // Clear fields for new favorite
            notesInput.value = '';
            tagsInput.value = '';
            document.getElementById('favoriteModalLabel').textContent = 'Add to Favorites';
        } else {
            // Load existing data
            fetch(`/api/favorite/${articleId}/status`)
                .then(response => response.json())
                .then(data => {
                    notesInput.value = data.notes || '';
                    tagsInput.value = data.tags || '';
                    document.getElementById('favoriteModalLabel').textContent = 'Edit Favorite';
                })
                .catch(error => {
                    console.error('Error loading favorite data:', error);
                });
        }

        // Setup save handler
        newSaveBtn.addEventListener('click', function() {
            saveFavorite(articleId, isNewFavorite, modal);
        });

        modal.show();
    }

    // Save favorite
    function saveFavorite(articleId, isNewFavorite, modal) {
        const notes = document.getElementById('favoriteNotes').value.trim();
        const tags = document.getElementById('favoriteTags').value.trim();

        const method = isNewFavorite ? 'POST' : 'PUT';
        const url = `/api/favorite/${articleId}`;

        fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                notes: notes,
                tags: tags
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                modal.hide();
                loadFavoriteStatus(articleId); // Refresh the display
                showToast(data.message, 'success');
            } else {
                showToast('Error saving favorite: ' + data.error, 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Network error occurred', 'error');
        });
    }

    // Simple toast notification
    function showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(toast);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 3000);
    }

    // Add this new function for ArXiv handlers
    function setupArxivHandlers(articleId) {
        const extractBtn = document.getElementById('extract-arxiv-btn');
        const deepSummaryBtn = document.getElementById('deep-summary-btn');

        if (extractBtn) {
            extractBtn.addEventListener('click', function() {
                extractArxivContent(articleId);
            });
        }

        if (deepSummaryBtn) {
            deepSummaryBtn.addEventListener('click', function() {
                requestDeepSummary(articleId);
            });
        }
    }

    // Add this new function for ArXiv content extraction
    function extractArxivContent(articleId) {
        const btn = document.getElementById('extract-arxiv-btn');
        if (!btn) return;

        // Show loading state
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Extracting...';
        btn.disabled = true;

        fetch(`/api/article/${articleId}/extract-arxiv`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('ArXiv content extraction started', 'success');
                btn.innerHTML = '<i class="fas fa-clock"></i> Processing...';

                // Reload article data after a few seconds to show updated status
                setTimeout(() => {
                    loadArticle(articleId);
                }, 3000);
            } else {
                showToast('Error: ' + data.error, 'error');
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Network error occurred', 'error');
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        });
    }

    // Add this new function for deep summary request
    function requestDeepSummary(articleId) {
        const btn = document.getElementById('deep-summary-btn');
        if (!btn) return;

        // Show loading state
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        btn.disabled = true;

        fetch(`/api/article/${articleId}/request-deep-summary`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Deep analysis generation started', 'success');
                btn.innerHTML = '<i class="fas fa-clock"></i> Processing...';

                // Reload article data after a few seconds to show updated status
                setTimeout(() => {
                    loadArticle(articleId);
                }, 5000);
            } else {
                showToast('Error: ' + data.error, 'error');
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Network error occurred', 'error');
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        });
    }

    // Initialize
    init();
});