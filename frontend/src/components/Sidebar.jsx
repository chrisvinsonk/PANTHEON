import { UserButton } from "@clerk/react";
import {
  Gavel,
  Landmark,
  LayoutDashboard,
  LineChart,
  ScrollText,
  Settings2,
  ShieldCheck,
  Vault,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";

const workspaceLinks = [
  { key: "command_centre", label: "Command Centre", icon: LayoutDashboard },
  { key: "chamber", label: "Council Chamber", icon: Landmark },
  { key: "conclaves", label: "Conclaves", icon: ScrollText },
  { key: "vault", label: "Knowledge Vault", icon: Vault },
  { key: "decisions", label: "Decision Register", icon: Gavel },
  { key: "performance", label: "Performance", icon: LineChart },
  { key: "operations", label: "Operations", icon: ShieldCheck },
];

const systemLinks = [
  { key: "configuration", label: "Configuration", icon: Settings2 },
];

function NavGroup({ label, links, activeView, onNavigate }) {
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="font-mono text-[9px] tracking-[0.2em] text-muted-foreground">
        {label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {links.map(({ key, label: itemLabel, icon: Icon }) => (
            <SidebarMenuItem key={key}>
              <SidebarMenuButton
                isActive={activeView === key}
                tooltip={itemLabel}
                onClick={() => onNavigate(key)}
                className="h-10"
              >
                <Icon className="size-4" />
                <span>{itemLabel}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

export default function Sidebar({ activeView, onNavigate }) {
  return (
    <ShadcnSidebar collapsible="icon" variant="sidebar">
      <SidebarHeader className="px-3 py-4">
        <div className="flex items-center gap-3 px-1">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-primary/30 bg-primary/10 font-heading text-lg text-primary">
            P
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="font-heading text-xs tracking-[0.13em] text-foreground">THE PANTHEON</p>
            <p className="mt-1 font-mono text-[9px] tracking-[0.15em] text-muted-foreground">
              FOUNDER CONSOLE
            </p>
          </div>
        </div>
      </SidebarHeader>
      <SidebarSeparator className="mx-0" />
      <SidebarContent>
        <NavGroup label="WORKSPACE" links={workspaceLinks} activeView={activeView} onNavigate={onNavigate} />
        <NavGroup label="SYSTEM" links={systemLinks} activeView={activeView} onNavigate={onNavigate} />
      </SidebarContent>
      <SidebarFooter className="gap-3 p-3">
        <Separator />
        <div className="flex min-w-0 items-center gap-3 px-1">
          <UserButton afterSignOutUrl="/" />
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="truncate text-xs font-medium text-foreground">Your account</p>
            <p className="truncate text-[11px] text-muted-foreground">Profile and sign out</p>
          </div>
        </div>
      </SidebarFooter>
    </ShadcnSidebar>
  );
}
