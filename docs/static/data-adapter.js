/**
 * Data Adapter for GitHub Pages Static Version
 * 
 * This module provides a compatibility layer that loads JSON files
 * instead of making API calls to the Flask backend.
 */

class StaticDataAdapter {
  constructor(dataPath = './data/') {
    this.dataPath = dataPath;
    this.cache = {};
  }

  /**
   * Load a JSON file
   */
  async loadJSON(filename) {
    if (this.cache[filename]) {
      return this.cache[filename];
    }

    try {
      const response = await fetch(`${this.dataPath}${filename}`);
      if (!response.ok) {
        throw new Error(`Failed to load ${filename}: ${response.status}`);
      }
      const data = await response.json();
      this.cache[filename] = data;
      return data;
    } catch (error) {
      console.error(`Error loading ${filename}:`, error);
      return [];
    }
  }

  /**
   * Get all persons
   */
  async getPersons() {
    return await this.loadJSON('persons.json');
  }

  /**
   * Get a single person by ID
   */
  async getPerson(id) {
    const persons = await this.getPersons();
    return persons.find(p => p.id === parseInt(id));
  }

  /**
   * Get all families
   */
  async getFamilies() {
    return await this.loadJSON('families.json');
  }

  /**
   * Get family children associations
   */
  async getFamilyChildren() {
    return await this.loadJSON('family_children.json');
  }

  /**
   * Get relationships (parent-child)
   */
  async getRelationships() {
    return await this.loadJSON('relationships.json');
  }

  /**
   * Get all events
   */
  async getEvents() {
    return await this.loadJSON('events.json');
  }

  /**
   * Get events for a specific person
   */
  async getPersonEvents(personId) {
    const events = await this.getEvents();
    return events.filter(e => e.person_id === parseInt(personId));
  }

  /**
   * Get all places
   */
  async getPlaces() {
    return await this.loadJSON('places.json');
  }

  /**
   * Get place variants
   */
  async getPlaceVariants() {
    return await this.loadJSON('place_variants.json');
  }

  /**
   * Get all notes
   */
  async getNotes() {
    return await this.loadJSON('notes.json');
  }

  /**
   * Get notes for a specific person
   */
  async getPersonNotes(personId) {
    const notes = await this.getNotes();
    return notes.filter(n => n.person_id === parseInt(personId));
  }

  /**
   * Get all media assets
   */
  async getMediaAssets() {
    return await this.loadJSON('media_assets.json');
  }

  /**
   * Get media links
   */
  async getMediaLinks() {
    return await this.loadJSON('media_links.json');
  }

  /**
   * Get media for a specific person
   */
  async getPersonMedia(personId) {
    const links = await this.getMediaLinks();
    const personLinks = links.filter(l => l.person_id === parseInt(personId));
    
    if (personLinks.length === 0) {
      return [];
    }
    
    const assets = await this.getMediaAssets();
    return personLinks.map(link => {
      const asset = assets.find(a => a.id === link.asset_id);
      return asset ? { ...asset, ...link } : null;
    }).filter(Boolean);
  }

  /**
   * Get data quality issues
   */
  async getDataQualityIssues() {
    return await this.loadJSON('dq_issues.json');
  }

  /**
   * Get date normalizations
   */
  async getDateNormalizations() {
    return await this.loadJSON('date_normalizations.json');
  }

  /**
   * Build a family tree structure
   */
  async buildFamilyTree() {
    const persons = await this.getPersons();
    const families = await this.getFamilies();
    const familyChildren = await this.getFamilyChildren();
    const relationships = await this.getRelationships();

    // Build a map of person ID to person object
    const personMap = new Map();
    persons.forEach(p => personMap.set(p.id, { ...p, children: [], parents: [] }));

    // Add family relationships
    families.forEach(family => {
      const husband = personMap.get(family.husband_person_id);
      const wife = personMap.get(family.wife_person_id);
      
      // Get children for this family
      const children = familyChildren
        .filter(fc => fc.family_id === family.id)
        .map(fc => personMap.get(fc.child_person_id))
        .filter(Boolean);
      
      // Link children to parents
      children.forEach(child => {
        if (husband) {
          child.parents.push(husband);
        }
        if (wife) {
          child.parents.push(wife);
        }
      });

      // Link parents to children
      if (husband) {
        husband.children.push(...children);
      }
      if (wife) {
        wife.children.push(...children);
      }
    });

    // Add direct parent-child relationships
    relationships.forEach(rel => {
      const parent = personMap.get(rel.parent_person_id);
      const child = personMap.get(rel.child_person_id);
      
      if (parent && child) {
        if (!parent.children.find(c => c.id === child.id)) {
          parent.children.push(child);
        }
        if (!child.parents.find(p => p.id === parent.id)) {
          child.parents.push(parent);
        }
      }
    });

    return Array.from(personMap.values());
  }

  /**
   * Search persons by name
   */
  async searchPersons(query) {
    const persons = await this.getPersons();
    const lowerQuery = query.toLowerCase();
    
    return persons.filter(p => {
      const fullName = `${p.given || ''} ${p.surname || ''}`.toLowerCase();
      return fullName.includes(lowerQuery) || 
             (p.given && p.given.toLowerCase().includes(lowerQuery)) ||
             (p.surname && p.surname.toLowerCase().includes(lowerQuery));
    });
  }

  /**
   * Get statistics
   */
  async getStatistics() {
    const persons = await this.getPersons();
    const families = await this.getFamilies();
    const events = await this.getEvents();
    const media = await this.getMediaAssets();

    return {
      totalPersons: persons.length,
      totalFamilies: families.length,
      totalEvents: events.length,
      totalMedia: media.length,
      maleCount: persons.filter(p => p.sex === 'M').length,
      femaleCount: persons.filter(p => p.sex === 'F').length,
      unknownGender: persons.filter(p => !p.sex || p.sex === 'U').length,
    };
  }
}

// Export for use in other scripts
window.dataAdapter = new StaticDataAdapter();
