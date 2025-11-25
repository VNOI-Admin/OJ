(function() {
    'use strict';

    class BlogTableOfContents {
        constructor() {
            this.tocContainer = null;
            this.contentArea = null;
            this.headings = [];
            this.activeHeading = null;
            
            this.init();
        }

        init() {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.setup());
            } else {
                this.setup();
            }
        }

        setup() {
            console.log('BlogTableOfContents: Starting setup');
            this.contentArea = document.querySelector('.blog-post-content');
            if (!this.contentArea) {
                console.error('Blog post content area not found');
                return;
            }

            console.log('BlogTableOfContents: Content area found');
            console.log('BlogTableOfContents: Content HTML:', this.contentArea.innerHTML.substring(0, 500));

            this.headings = Array.from(this.contentArea.querySelectorAll('h1, h2, h3, h4, h5, h6'));
            
            console.log('BlogTableOfContents: Found headings:', this.headings.length);
            this.headings.forEach((h, i) => {
                console.log(`Heading ${i + 1}:`, h.tagName, h.textContent, 'ID:', h.id);
            });
            
            if (this.headings.length === 0) {
                this.removeTocContainer();
                return;
            }

            this.addHeadingIds();

            this.createTocContainer();

            this.generateToc();

            this.setupScrollSpy();

            this.setupSmoothScrolling();
            
            console.log('BlogTableOfContents: Setup complete');
        }

        addHeadingIds() {
            this.headings.forEach((heading, index) => {
                if (!heading.id) {
                    const slug = this.createSlug(heading.textContent);
                    heading.id = slug || `heading-${index}`;
                }
            });
        }

        createSlug(text) {
            return text
                .toLowerCase()
                .trim()
                .replace(/[^\w\s-]/g, '')
                .replace(/[\s_-]+/g, '-')
                .replace(/^-+|-+$/g, '');
        }

        createTocContainer() {
            let existingSidebar = document.querySelector('.blog-toc-sidebar-container');
            existingSidebar.innerHTML = `
            <div class="blog-toc-sidebar" id="table-of-contents">

            <div class="blog-toc-header">
                <h3>Table of Contents</h3>
            </div>
            <div class="blog-toc-nav"></div>
            </div>
            `;
            this.tocContainer = existingSidebar.querySelector('.blog-toc-nav');
        }
        removeTocContainer() {
            const existingSidebar = document.querySelector('.blog-toc-sidebar-container');
            if (existingSidebar) {
                existingSidebar.remove();
            }
        }

        generateToc() {
            if (!this.tocContainer) return;

            const tocList = document.createElement('ul');
            tocList.className = 'blog-toc-list';

            if (this.headings.length === 0) return;

            const minLevel = Math.min(...this.headings.map(h => parseInt(h.tagName.substring(1))));
            let currentLevel = minLevel;
            let currentList = tocList;
            const listStack = [{ level: minLevel, list: tocList }];

            this.headings.forEach((heading) => {
                const level = parseInt(heading.tagName.substring(1));
                const listItem = document.createElement('li');
                listItem.className = 'blog-toc-item';

                const link = document.createElement('a');
                link.href = `#${heading.id}`;
                link.textContent = heading.textContent;
                link.title = heading.textContent; 
                link.className = 'blog-toc-link';
                link.setAttribute('data-target', heading.id);

                listItem.appendChild(link);

                if (level > currentLevel) {
                    const nestedList = document.createElement('ul');
                    nestedList.className = 'blog-toc-list blog-toc-nested';
                    const lastItem = currentList.lastElementChild;
                    if (lastItem) {
                        lastItem.appendChild(nestedList);
                    } else {
                        currentList.appendChild(nestedList);
                    }
                    currentList = nestedList;
                    listStack.push({ level: level, list: nestedList });
                } else if (level < currentLevel) {
                    while (listStack.length > 1 && listStack[listStack.length - 1].level > level) {
                        listStack.pop();
                    }
                    currentList = listStack[listStack.length - 1].list;
                }

                currentList.appendChild(listItem);
                currentLevel = level;
            });

            this.tocContainer.appendChild(tocList);
        }

        setupScrollSpy() {
            const options = {
                root: null,
                rootMargin: '-80px 0px -80% 0px',
                threshold: 0
            };

            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    const id = entry.target.id;
                    const tocLink = this.tocContainer.querySelector(`a[data-target="${id}"]`);
                    
                    if (entry.isIntersecting) {
                        this.tocContainer.querySelectorAll('.blog-toc-link').forEach(link => {
                            link.classList.remove('active');
                        });
                        
                        if (tocLink) {
                            tocLink.classList.add('active');
                        }
                    }
                });
            }, options);

            this.headings.forEach(heading => {
                observer.observe(heading);
            });
        }

        setupSmoothScrolling() {
            this.tocContainer.querySelectorAll('.blog-toc-link').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const targetId = link.getAttribute('data-target');
                    const targetElement = document.getElementById(targetId);
                    
                    if (targetElement) {
                        const offset = 80; 
                        const targetPosition = targetElement.getBoundingClientRect().top + window.pageYOffset - offset;
                        
                        window.scrollTo({
                            top: targetPosition,
                            behavior: 'smooth'
                        });
                    }
                });
            });
        }
    }

    new BlogTableOfContents();
})();
