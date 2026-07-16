import { test, expect } from '@playwright/test';

test.describe('SkillDeck dark/light mode toggle', () => {
  test('defaults to light mode and honors OS dark preference', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).not.toHaveClass(/dark/);

    await page.emulateMedia({ colorScheme: 'dark' });
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/dark/);
  });

  test('toggle button switches theme and persists across reload', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/');

    const html = page.locator('html');
    const toggle = page.locator('#theme-toggle');
    await expect(toggle).toBeVisible();
    await expect(html).not.toHaveClass(/dark/);

    // Switch to dark
    await toggle.click();
    await expect(html).toHaveClass(/dark/);
    await expect(page.locator('body')).toHaveCSS(
      'background-color',
      /(rgb\(9,\s*9,\s*11\)|oklch\(0\.141\s+0\.005\s+285\.823\)|oklab\(0\.144038\s+0\.00135843\s+-0\.00479323\))/
    );

    // Persists across reload via localStorage
    await page.reload();
    await expect(html).toHaveClass(/dark/);
    expect(await page.evaluate(() => localStorage.getItem('skilldeck_theme'))).toBe('dark');

    // Switch back to light
    await toggle.click();
    await expect(html).not.toHaveClass(/dark/);
    await page.reload();
    await expect(html).not.toHaveClass(/dark/);
    expect(await page.evaluate(() => localStorage.getItem('skilldeck_theme'))).toBe('light');
  });

  test('stored preference overrides OS preference on every page', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');
    await page.locator('#theme-toggle').click(); // OS wants dark, user picks light
    await expect(page.locator('html')).not.toHaveClass(/dark/);

    for (const path of ['/about']) {
      await page.goto(path);
      await expect(page.locator('html')).not.toHaveClass(/dark/);
      await expect(page.locator('#theme-toggle')).toBeVisible();
    }
  });
});
