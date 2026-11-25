// The tabs of a panel, links to its pages, the current one marked.

type TabsProps = { tabs: { label: string; href: string }[]; current: string };

export function Tabs({ tabs, current }: TabsProps) {
  return (
    <nav className="tabs">
      {tabs.map(tab => (
        <a key={tab.href} href={tab.href} aria-current={tab.href === current ? 'page' : undefined}>{tab.label}</a>
      ))}
    </nav>
  );
}
