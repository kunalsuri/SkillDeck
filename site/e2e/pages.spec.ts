import { test, expect } from '@playwright/test';

test.describe('SkillDeck E2E Pages Test Suite', () => {
  test('should load landing page, show hero, and render publisher organizations grid', async ({ page }) => {
    // Navigate to landing page
    await page.goto('/');
    await page.waitForTimeout(500);
    
    // Check header logo link contains SkillDeck
    await expect(page.locator('header a').first()).toContainText('SkillDeck');
    
    // Check main hero title text
    await expect(page.locator('main h1').first()).toContainText('The Curated');
    
    // SKILL Publishing Organizations grid title must exist
    const gridTitle = page.locator('main h2').first();
    await expect(gridTitle).toContainText('SKILL Publishing Organizations');

    // Confirm publisher grid links exist
    await expect(page.locator('a[href="#google"]').first()).toBeVisible();
    await expect(page.locator('a[href="#anthropic"]').first()).toBeVisible();
  });

  test('should navigate to skill detail page via SkillExplorer and render detail elements', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(500);
    
    // Find the link to view full documentation in the explorer details pane and click it
    const viewDocLink = page.getByRole('link', { name: /View full documentation/i }).first();
    await viewDocLink.click();
    
    // Should navigate to detail page
    await expect(page).toHaveURL(/\/skill\/.*/);
    
    // Verify detail metadata is visible (title is rendered in an h3 tag)
    await expect(page.locator('main h3').first()).toBeVisible();
    
    // Open the trust details panel to make the badge visible
    await page.locator('.trust-summary summary').click();
    await expect(page.getByText(/Official|Community|Partner/i).first()).toBeVisible();
    await expect(page.getByText(/View Upstream Source/i).first()).toBeVisible();
    await expect(page.getByText(/Try asking your assistant/i).first()).toBeVisible();
  });

  test('should load the combined about page containing upstream sources and methodology legends', async ({ page }) => {
    await page.goto('/about');
    await expect(page.locator('main h1').first()).toContainText('About SkillDeck');
    
    // Upstream sources table should be present
    await expect(page.locator('table').first()).toBeVisible();
    await expect(page.getByText(/Kind/i).first()).toBeVisible();

    // Badges legend should be present
    await expect(page.getByText(/Verified Core/i).first()).toBeVisible();
  });

  test('should load the Skill Doctor page with header and textarea', async ({ page }) => {
    await page.goto('/doctor');
    await expect(page.locator('header a').first()).toContainText('SkillDeck');
    await expect(page.locator('main h1').first()).toContainText('Skill Doctor');
    await expect(page.locator('#skill-doctor-input')).toBeVisible();
  });

  test('Skill Doctor flags a missing description with SD04', async ({ page }) => {
    await page.goto('/doctor');
    await page.locator('#skill-doctor-input').fill('---\nname: my-skill\n---\nSome body content.');
    await page.getByRole('button', { name: /Check Skill/i }).click();
    await expect(page.getByText('SD04')).toBeVisible();
    await expect(page.getByText(/Missing "description" field/i)).toBeVisible();
  });

  test('Skill Doctor shows a ready verdict for a well-formed skill', async ({ page }) => {
    await page.goto('/doctor');
    const wellFormed = [
      '---',
      'name: quarterly-report-writer',
      'description: Creates polished quarterly reports from raw spreadsheets. Use this when users request a formatted report or need to summarize spreadsheet data quickly.',
      '---',
      '',
      'Concise, well-scoped instructions for generating the report.',
    ].join('\n');
    await page.locator('#skill-doctor-input').fill(wellFormed);
    await page.getByRole('button', { name: /Check Skill/i }).click();
    await expect(page.getByText('Ready', { exact: true })).toBeVisible();
  });

  test('should load the terminology comparison table inside the collapsible concepts accordion', async ({ page }) => {
    await page.goto('/about');
    
    // Locate the details block for concepts map and click summary
    const summary = page.locator('details summary').first();
    await expect(summary).toContainText('Cross-Tool Terminology Map');
    await summary.click();

    // Verify comparison table headers
    const table = page.locator('details table');
    await expect(table).toBeVisible();

    const headers = table.locator('thead th');
    await expect(headers).toHaveCount(7); // "Mechanism" + 6 tools
    await expect(headers.filter({ hasText: 'Claude Code' })).toBeVisible();
    await expect(headers.filter({ hasText: 'VS Code / Copilot' })).toBeVisible();
    await expect(headers.filter({ hasText: 'Cursor' })).toBeVisible();
  });

  test('About nav link works from the homepage', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'About' }).click();
    await expect(page).toHaveURL(/\/about/);
    await expect(page.locator('main h1').first()).toContainText('About SkillDeck');
  });
});
