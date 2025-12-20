/**
 * In-App Help System
 * Provides contextual help and documentation for family tree visualizations
 */

const HelpContent = {
  // Tree visualization types
  visualizations: {
    miniTree: {
      title: "Mini Tree View",
      description: "A simple, fast visualization showing immediate family connections.",
      insights: [
        "View direct parent-child relationships at a glance",
        "Quickly identify immediate family members",
        "See basic genealogical structure without overwhelming detail"
      ],
      bestFor: "Quick navigation and understanding immediate family connections",
      icon: "🌳"
    },
    elkLayered: {
      title: "Layered Layout (ELK)",
      description: "Hierarchical tree layout that organizes people by generation.",
      insights: [
        "Clearly shows generational hierarchy from ancestors to descendants",
        "Ideal for understanding family lineage and descent patterns",
        "Reveals ancestral lines and how families branch over time",
        "Best for identifying convergences where distant relatives marry"
      ],
      bestFor: "Understanding family structure across multiple generations and seeing generational patterns",
      icon: "📊"
    },
    breadthfirst: {
      title: "Breadthfirst Layout",
      description: "Spreads the tree outward from a central person, showing connections level by level.",
      insights: [
        "Centers on a specific individual, showing their network of relationships",
        "Displays equal-distance relationships at the same visual level",
        "Helpful for understanding a person's place within the larger family",
        "Shows how far connections extend from the root person"
      ],
      bestFor: "Exploring relationships from a specific person's perspective",
      icon: "🎯"
    },
    concentric: {
      title: "Concentric Layout",
      description: "Arranges family members in circular rings based on their relationship distance.",
      insights: [
        "Visualizes 'relationship distance' from a central person",
        "Creates a radial pattern that shows family connections spreading outward",
        "Helps identify close vs. distant relatives spatially",
        "Useful for understanding the scope of family networks"
      ],
      bestFor: "Understanding relationship proximity and family network scope",
      icon: "⭕"
    },
    cose: {
      title: "Force-Directed Layout (COSE)",
      description: "Uses physics-based simulation to position nodes, revealing organic patterns.",
      insights: [
        "Naturally clusters closely related family groups",
        "Reveals hidden patterns and relationship convergences",
        "Shows 'relationship density' - areas with many interconnections",
        "Excellent for discovering where different family lines intersect",
        "Highlights complex relationships like cousins marrying or multiple marriages"
      ],
      bestFor: "Discovering hidden patterns, convergences, and complex family interconnections",
      icon: "🔮"
    }
  },

  // Workflow guides
  workflows: {
    browseToPerson: {
      title: "Viewing Person Details",
      steps: [
        "Select a person from the list on the left",
        "Details panel shows all known information",
        "Parents and children are listed with their names (no IDs needed)",
        "Click 'Save' after making any edits"
      ]
    },
    browseToMedia: {
      title: "Adding Media to a Person",
      steps: [
        "Select the person you want to add media to",
        "Scroll to the 'Media' section in the details panel",
        "Click 'Upload Media' to select photos, documents, or other files",
        "Files are automatically linked to the selected person",
        "View thumbnails of images directly in the person's details"
      ]
    },
    findingRelationships: {
      title: "Finding Family Connections",
      steps: [
        "Use Tree v2 view for advanced relationship exploration",
        "Select different layouts to reveal different patterns:",
        "  • Layered: See generational structure",
        "  • Force-directed: Discover convergences",
        "Marriages are shown as diamond nodes (⚭) connecting spouses",
        "Lines show parent-child relationships",
        "Look for multiple paths between people to find convergences"
      ]
    },
    convergences: {
      title: "Identifying Relationship Convergences",
      description: "Convergences occur when family lines reconnect, such as distant cousins marrying.",
      steps: [
        "Use the COSE (Force) or ELK layout in Tree v2",
        "Look for people who appear connected through multiple paths",
        "Diamond marriage nodes (⚭) with many connections indicate convergences",
        "These patterns show how separate family branches have intertwined"
      ]
    }
  },

  // General tips
  tips: {
    noIds: {
      title: "Focus on Relationships, Not IDs",
      content: "The interface emphasizes names and connections. Person IDs are shown minimally for technical reference only. Navigate using names and relationships."
    },
    marriages: {
      title: "Understanding Marriage Connections",
      content: "Marriages are shown as diamond nodes (⚭) in the graph view. Spouses connect to the marriage node, and children connect from it, clearly showing family units."
    },
    quality: {
      title: "Data Quality Indicators",
      content: "Person nodes are color-coded by data quality: darker blue = complete information (name, birth), lighter blue = partial information. This helps you identify where more research is needed."
    }
  }
};

class HelpModal {
  constructor() {
    this.modal = null;
    this.currentContext = 'general';
    this.init();
  }

  init() {
    // Create modal HTML
    const modal = document.createElement('div');
    modal.id = 'helpModal';
    modal.className = 'helpModal hidden';
    modal.innerHTML = `
      <div class="helpModalOverlay"></div>
      <div class="helpModalContent">
        <div class="helpModalHeader">
          <h2>📖 In-App Help</h2>
          <button class="helpModalClose" aria-label="Close help">&times;</button>
        </div>
        <div class="helpModalBody">
          <nav class="helpNav">
            <button class="helpNavItem active" data-section="visualizations">Tree Visualizations</button>
            <button class="helpNavItem" data-section="workflows">Workflows</button>
            <button class="helpNavItem" data-section="tips">Tips & Tricks</button>
          </nav>
          <div class="helpContent" id="helpContentArea"></div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    this.modal = modal;

    // Wire up events
    modal.querySelector('.helpModalClose').addEventListener('click', () => this.hide());
    modal.querySelector('.helpModalOverlay').addEventListener('click', () => this.hide());
    
    modal.querySelectorAll('.helpNavItem').forEach(btn => {
      btn.addEventListener('click', (e) => {
        modal.querySelectorAll('.helpNavItem').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.showSection(e.target.dataset.section);
      });
    });

    // ESC key to close
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !this.modal.classList.contains('hidden')) {
        this.hide();
      }
    });
  }

  show(context = 'general') {
    this.currentContext = context;
    this.modal.classList.remove('hidden');
    this.showSection('visualizations');
    document.body.style.overflow = 'hidden';
  }

  hide() {
    this.modal.classList.add('hidden');
    document.body.style.overflow = '';
  }

  showSection(section) {
    const contentArea = document.getElementById('helpContentArea');
    let html = '';

    if (section === 'visualizations') {
      html = '<div class="helpSection">';
      html += '<h3>Tree Visualization Types</h3>';
      html += '<p class="helpIntro">Each visualization type reveals different aspects of your family tree. Choose the one that best fits what you\'re trying to discover.</p>';
      
      for (const [key, viz] of Object.entries(HelpContent.visualizations)) {
        html += `
          <div class="helpCard">
            <div class="helpCardHeader">
              <span class="helpCardIcon">${viz.icon}</span>
              <h4>${viz.title}</h4>
            </div>
            <p class="helpCardDescription">${viz.description}</p>
            <div class="helpCardSection">
              <strong>Insights You'll Gain:</strong>
              <ul>
                ${viz.insights.map(i => `<li>${i}</li>`).join('')}
              </ul>
            </div>
            <div class="helpCardBest">
              <strong>Best For:</strong> ${viz.bestFor}
            </div>
          </div>
        `;
      }
      html += '</div>';
    } else if (section === 'workflows') {
      html = '<div class="helpSection">';
      html += '<h3>Common Workflows</h3>';
      html += '<p class="helpIntro">Step-by-step guides for common tasks.</p>';
      
      for (const [key, workflow] of Object.entries(HelpContent.workflows)) {
        html += `
          <div class="helpCard">
            <h4>${workflow.title}</h4>
            ${workflow.description ? `<p class="helpCardDescription">${workflow.description}</p>` : ''}
            <ol class="helpSteps">
              ${workflow.steps.map(s => `<li>${s}</li>`).join('')}
            </ol>
          </div>
        `;
      }
      html += '</div>';
    } else if (section === 'tips') {
      html = '<div class="helpSection">';
      html += '<h3>Tips & Tricks</h3>';
      
      for (const [key, tip] of Object.entries(HelpContent.tips)) {
        html += `
          <div class="helpCard">
            <h4>${tip.title}</h4>
            <p>${tip.content}</p>
          </div>
        `;
      }
      html += '</div>';
    }

    contentArea.innerHTML = html;
  }
}

// Initialize global help system
let helpSystem = null;

function initHelp() {
  if (!helpSystem) {
    helpSystem = new HelpModal();
  }
  return helpSystem;
}

function showHelp(context = 'general') {
  const help = initHelp();
  help.show(context);
}

// Make available globally
window.showHelp = showHelp;
window.initHelp = initHelp;
