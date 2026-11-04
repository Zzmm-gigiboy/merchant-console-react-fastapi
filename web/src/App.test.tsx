import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from './App';

const mockProducts = [
  { id: 1, name: 'Canvas Tote', category: 'Accessories', price: 18.5, stock: 22 },
  { id: 2, name: 'Ceramic Mug', category: 'Home', price: 12.0, stock: 8 },
  { id: 3, name: 'Desk Lamp', category: 'Home', price: 44.0, stock: 0 },
];

const mockStats = {
  count: 3,
  out_of_stock: 1,
  inventory_value: 503.0,
};

describe('Merchant Console App Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders initial loading state and dashboard header', () => {
    // Return unresolved promise to observe loading state
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: /merchant console/i })).toBeInTheDocument();
    expect(screen.getByText(/demo \/ merchant operations/i)).toBeInTheDocument();
    expect(screen.getByText(/track catalog, stock, and promotional pricing/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/loading inventory/i);
  });

  it('fetches and displays merchant product catalog and inventory statistics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/api/products')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockProducts),
          } as Response);
        }
        if (url.includes('/api/stats')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockStats),
          } as Response);
        }
        return Promise.reject(new Error(`Unhandled request: ${url}`));
      })
    );

    render(<App />);

    // Wait for table to render after loading completes
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    // Verify statistics cards
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('$503.00')).toBeInTheDocument();

    // Verify table items
    expect(screen.getByText('Canvas Tote')).toBeInTheDocument();
    expect(screen.getByText('Accessories')).toBeInTheDocument();
    expect(screen.getByText('$18.50')).toBeInTheDocument();

    expect(screen.getByText('Ceramic Mug')).toBeInTheDocument();
    expect(screen.getByText('Desk Lamp')).toBeInTheDocument();
  });

  it('renders status indicators for in-stock and out-of-stock items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/api/products')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockProducts),
          } as Response);
        }
        if (url.includes('/api/stats')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockStats),
          } as Response);
        }
        return Promise.reject(new Error('Unknown url'));
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    // In-stock items display stock quantity with standard pill
    const inStockPill = screen.getByText('22');
    expect(inStockPill).toHaveClass('pill');

    // Out-of-stock item displays 'Out' with warn pill
    const outOfStockPill = screen.getByText('Out');
    expect(outOfStockPill).toHaveClass('pill warn');
  });

  it('filters merchant products by search query across name and category', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/api/products')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockProducts),
          } as Response);
        }
        if (url.includes('/api/stats')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockStats),
          } as Response);
        }
        return Promise.reject(new Error('Unknown url'));
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Canvas Tote')).toBeInTheDocument();
    });

    const searchInput = screen.getByLabelText(/filter catalog/i);

    // Search by product name
    await user.type(searchInput, 'Canvas');
    expect(screen.getByText('Canvas Tote')).toBeInTheDocument();
    expect(screen.queryByText('Ceramic Mug')).not.toBeInTheDocument();
    expect(screen.queryByText('Desk Lamp')).not.toBeInTheDocument();

    // Clear search and search by category
    await user.clear(searchInput);
    await user.type(searchInput, 'Home');
    expect(screen.queryByText('Canvas Tote')).not.toBeInTheDocument();
    expect(screen.getByText('Ceramic Mug')).toBeInTheDocument();
    expect(screen.getByText('Desk Lamp')).toBeInTheDocument();

    // Search with no matches
    await user.clear(searchInput);
    await user.type(searchInput, 'ZzzNotExist');
    expect(screen.getByText(/no matching products/i)).toBeInTheDocument();
  });

  it('displays alert banner when API fetch encounters network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network connection refused'))));

    render(<App />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveClass('alert');
    expect(alert).toHaveTextContent(/network connection refused/i);
  });

  it('submits new product through form and refreshes list', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.includes('/api/products')) {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ id: 4, name: 'Leather Wallet', category: 'Accessories', price: 45, stock: 10 }),
        } as Response);
      }
      if (url.includes('/api/products')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockProducts),
        } as Response);
      }
      if (url.includes('/api/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockStats),
        } as Response);
      }
      return Promise.reject(new Error('Unknown url'));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText(/product name/i);
    const categoryInput = screen.getByLabelText(/^category/i);
    const priceInput = screen.getByLabelText(/price/i);
    const stockInput = screen.getByLabelText(/stock/i);
    const submitButton = screen.getByRole('button', { name: /add to catalog/i });

    await user.type(nameInput, 'Leather Wallet');
    await user.clear(categoryInput);
    await user.type(categoryInput, 'Accessories');
    await user.type(priceInput, '45');
    await user.clear(stockInput);
    await user.type(stockInput, '10');

    await user.click(submitButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/products'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'Leather Wallet', category: 'Accessories', price: 45, stock: 10 }),
        })
      );
    });
  });

  it('triggers discount preview calculation and displays updated pricing', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.includes('/api/discount-preview')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ original: 100, discount_percent: 15, final: 85.0 }),
        } as Response);
      }
      if (url.includes('/api/products')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockProducts),
        } as Response);
      }
      if (url.includes('/api/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockStats),
        } as Response);
      }
      return Promise.reject(new Error('Unknown url'));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    const discountInput = screen.getByLabelText(/discount percentage/i);
    await user.clear(discountInput);
    await user.type(discountInput, '15');

    const previewButton = screen.getByRole('button', { name: /^preview$/i });
    await user.click(previewButton);

    const statusMsg = await screen.findByRole('status');
    expect(statusMsg).toHaveTextContent(/new price: \$85\.00/i);
  });

  it('handles stock edit through prompt dialog and invokes patch API', async () => {
    const user = userEvent.setup();
    const promptMock = vi.fn(() => '35');
    vi.stubGlobal('prompt', promptMock);

    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH' && url.includes('/api/products/1/stock')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 1, stock: 35 }),
        } as Response);
      }
      if (url.includes('/api/products')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockProducts),
        } as Response);
      }
      if (url.includes('/api/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockStats),
        } as Response);
      }
      return Promise.reject(new Error('Unknown url'));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByRole('button', { name: /edit stock/i });
    await user.click(editButtons[0]);

    expect(promptMock).toHaveBeenCalledWith('New stock for Canvas Tote', '22');
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/products/1/stock'),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ stock: 35 }),
        })
      );
    });
  });

  it('re-fetches catalog and metrics when refresh button is clicked', async () => {
    const user = userEvent.setup();
    let callCount = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/api/products') || url.includes('/api/stats')) {
        callCount++;
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(url.includes('/api/products') ? mockProducts : mockStats),
        } as Response);
      }
      return Promise.reject(new Error('Unknown url'));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    const initialCalls = callCount;
    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshButton);

    await waitFor(() => {
      expect(callCount).toBeGreaterThan(initialCalls);
    });
  });
});
