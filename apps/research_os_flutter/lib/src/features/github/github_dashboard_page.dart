import 'package:flutter/material.dart';

import '../../api/research_os_api_client.dart';

class GitHubDashboardPage extends StatefulWidget {
  const GitHubDashboardPage({required this.apiClient, super.key});

  final ResearchOSApiClient apiClient;

  @override
  State<GitHubDashboardPage> createState() => _GitHubDashboardPageState();
}

class _GitHubDashboardPageState extends State<GitHubDashboardPage> {
  final _repositoryController = TextEditingController(
    text: 'phakphoum38-stack/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH',
  );

  bool _loading = true;
  bool _loadingAccounts = true;
  bool _showRunnerTarget = true;
  String? _error;
  Map<String, dynamic>? _dashboard;
  List<Map<String, dynamic>> _accounts = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> _repositories = <Map<String, dynamic>>[];
  String? _selectedAccountId;
  String? _selectedRepository;

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  List<Map<String, dynamic>> _mapItems(dynamic value) {
    if (value is! List) return <Map<String, dynamic>>[];
    return value.whereType<Map>().map((item) =>
        item.map((key, value) => MapEntry(key.toString(), value))).toList(growable: false);
  }

  Future<void> _loadAccounts() async {
    try {
      final result = await widget.apiClient.getGitHubAccounts();
      final accounts = _mapItems(result['accounts']);
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _selectedAccountId = accounts.isEmpty ? null : accounts.first['id']?.toString();
        _loadingAccounts = false;
      });
      if (_selectedAccountId != null) {
        await _loadRepositories(_selectedAccountId!, refreshDashboard: true);
      } else {
        await _refresh();
      }
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _loadingAccounts = false;
        _error = 'โหลดบัญชี GitHub ไม่สำเร็จ: $error';
      });
    }
  }

  Future<void> _loadRepositories(String accountId, {bool refreshDashboard = false}) async {
    setState(() {
      _loading = true;
      _error = null;
      _dashboard = null;
      _repositories = <Map<String, dynamic>>[];
    });
    try {
      final repositories = <Map<String, dynamic>>[];
      var page = 1;
      var hasMore = true;
      while (hasMore && page <= 100) {
        final result = await widget.apiClient.getGitHubRepositories(accountId: accountId, page: page);
        repositories.addAll(_mapItems(result['repositories']));
        hasMore = result['has_more'] == true;
        page++;
      }
      if (!mounted) return;
      final selected = repositories.any((item) => item['full_name'] == _selectedRepository)
          ? _selectedRepository
          : (repositories.isEmpty ? null : repositories.first['full_name']?.toString());
      setState(() {
        _repositories = repositories;
        _selectedRepository = selected;
        if (selected != null) _repositoryController.text = selected;
        _loading = false;
      });
      if (refreshDashboard && selected != null) await _refresh();
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'โหลด Repository ของบัญชีที่เลือกไม่สำเร็จ: $error';
        _loading = false;
      });
    }
  }

  Future<void> _selectAccount(String? accountId) async {
    if (accountId == null || accountId == _selectedAccountId) return;
    setState(() => _selectedAccountId = accountId);
    await _loadRepositories(accountId, refreshDashboard: true);
  }

  @override
  void dispose() {
    _repositoryController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.apiClient.getGitHubDashboard(
        repository: _repositoryController.text,
        accountId: _selectedAccountId,
      );
      if (!mounted) return;
      setState(() {
        _dashboard = result;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  List<Map<String, dynamic>> _items(String key) {
    final value = _dashboard?[key];
    if (value is! List) return const <Map<String, dynamic>>[];
    return value.whereType<Map>().map((item) {
      return item.map((key, value) => MapEntry(key.toString(), value));
    }).toList(growable: false);
  }

  @override
  Widget build(BuildContext context) {
    final workflows = _items('workflow_runs');
    final commits = _items('commits');
    final pulls = _items('pull_requests');

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 40),
        children: <Widget>[
          _Heading(
            icon: Icons.account_tree_outlined,
            title: 'GitHub Control Center',
            subtitle: 'ติดตาม Repository, Workflow, Commit และ Pull Request ผ่าน Research OS API',
            action: IconButton(
              tooltip: 'Refresh',
              onPressed: _loading ? null : _refresh,
              icon: const Icon(Icons.refresh),
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: <Widget>[
              Expanded(
                child: Text('Runner target', style: Theme.of(context).textTheme.titleLarge),
              ),
              OutlinedButton.icon(
                onPressed: () => setState(() => _showRunnerTarget = !_showRunnerTarget),
                icon: const Icon(Icons.terminal),
                label: Text(_showRunnerTarget ? 'ซ่อน Runner' : 'Runner'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (_showRunnerTarget) Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  if (_loadingAccounts)
                    const LinearProgressIndicator()
                  else if (_accounts.isNotEmpty) ...<Widget>[
                    DropdownButtonFormField<String>(
                      key: ValueKey<String?>(_selectedAccountId),
                      initialValue: _selectedAccountId,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'บัญชี GitHub', prefixIcon: Icon(Icons.person_outline)),
                      items: _accounts.map((account) {
                        final id = account['id']?.toString() ?? '';
                        final login = account['login']?.toString() ?? '';
                        final label = account['label']?.toString() ?? login;
                        return DropdownMenuItem<String>(
                          value: id,
                          child: Text(login.isEmpty ? label : '$label (@$login)', overflow: TextOverflow.ellipsis),
                        );
                      }).toList(growable: false),
                      onChanged: _loading ? null : _selectAccount,
                    ),
                    const SizedBox(height: 12),
                  ],
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Expanded(
                        child: _repositories.isNotEmpty
                            ? DropdownButtonFormField<String>(
                                key: ValueKey<String?>(_selectedRepository),
                                initialValue: _selectedRepository,
                                isExpanded: true,
                                decoration: const InputDecoration(labelText: 'Repository', prefixIcon: Icon(Icons.account_tree_outlined)),
                                items: _repositories.map((repository) {
                                  final name = repository['full_name']?.toString() ?? '';
                                  return DropdownMenuItem<String>(value: name, child: Text(name, overflow: TextOverflow.ellipsis));
                                }).toList(growable: false),
                                onChanged: _loading ? null : (value) {
                                  if (value == null) return;
                                  setState(() {
                                    _selectedRepository = value;
                                    _repositoryController.text = value;
                                  });
                                  _refresh();
                                },
                              )
                            : TextField(
                                controller: _repositoryController,
                                enabled: !_loading,
                                decoration: const InputDecoration(labelText: 'Repository', hintText: 'owner/name', prefixIcon: Icon(Icons.account_tree_outlined)),
                                onSubmitted: (_) => _refresh(),
                              ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(onPressed: _loading ? null : _refresh, icon: const Icon(Icons.search), label: const Text('โหลด')),
                    ],
                  ),
                  if (_accounts.isEmpty && !_loadingAccounts) ...<Widget>[
                    const SizedBox(height: 8),
                    const Text('ยังไม่มีบัญชี GitHub ที่กำหนดไว้บน API: ตั้งค่า RESEARCH_OS_GITHUB_ACCOUNTS_JSON เพื่อเลือกหลายบัญชี'),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 18),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.error_outline),
                title: const Text('โหลดข้อมูล GitHub ไม่สำเร็จ'),
                subtitle: Text(_error!),
                trailing: IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
              ),
            ),
          if (_dashboard != null) ...<Widget>[
            Text('Repository overview', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            LayoutBuilder(
              builder: (context, constraints) {
                final columns = constraints.maxWidth >= 900
                    ? 4
                    : constraints.maxWidth >= 560
                        ? 2
                        : 1;
                return GridView.count(
                  crossAxisCount: columns,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 12,
                  crossAxisSpacing: 12,
                  mainAxisExtent: 104,
                  children: <Widget>[
                    _MetricCard(title: 'Default branch', value: '${_dashboard?['default_branch'] ?? '-'}', icon: Icons.call_split),
                    _MetricCard(title: 'Visibility', value: '${_dashboard?['visibility'] ?? '-'}', icon: Icons.visibility_outlined),
                    _MetricCard(title: 'Open Issues', value: '${_dashboard?['open_issues_count'] ?? 0}', icon: Icons.error_outline),
                    _MetricCard(title: 'Forks', value: '${_dashboard?['forks_count'] ?? 0}', icon: Icons.fork_right),
                  ],
                );
              },
            ),
            const SizedBox(height: 26),
            _SectionTitle(title: 'Latest workflows', count: workflows.length),
            ...workflows.map((item) => _WorkflowTile(item: item)),
            if (workflows.isEmpty) const _EmptyCard(label: 'ยังไม่มี Workflow'),
            const SizedBox(height: 26),
            _SectionTitle(title: 'Latest commits', count: commits.length),
            ...commits.map(
              (item) => Card(
                child: ListTile(
                  leading: const Icon(Icons.commit),
                  title: Text('${item['message'] ?? '-'}'),
                  subtitle: Text('${item['sha'] ?? ''} • ${item['author'] ?? 'unknown'}'),
                ),
              ),
            ),
            if (commits.isEmpty) const _EmptyCard(label: 'ยังไม่มี Commit'),
            const SizedBox(height: 26),
            _SectionTitle(title: 'Open pull requests', count: pulls.length),
            ...pulls.map(
              (item) => Card(
                child: ListTile(
                  leading: const Icon(Icons.merge_type),
                  title: Text('#${item['number'] ?? '-'} ${item['title'] ?? ''}'),
                  subtitle: Text('${item['author'] ?? 'unknown'}'),
                  trailing: Chip(label: Text(item['draft'] == true ? 'Draft' : 'Open')),
                ),
              ),
            ),
            if (pulls.isEmpty) const _EmptyCard(label: 'ไม่มี Pull Request ที่เปิดอยู่'),
          ],
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading({required this.icon, required this.title, required this.subtitle, required this.action});
  final IconData icon;
  final String title;
  final String subtitle;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: 46,
          height: 46,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 4),
              Text(subtitle, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
        action,
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.title, required this.value, required this.icon});
  final String title;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: <Widget>[
            Icon(icon, size: 30),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
                  Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleLarge),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, required this.count});
  final String title;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(title, style: Theme.of(context).textTheme.titleLarge)),
          Chip(label: Text('$count')),
        ],
      ),
    );
  }
}

class _WorkflowTile extends StatelessWidget {
  const _WorkflowTile({required this.item});
  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final conclusion = item['conclusion']?.toString();
    final status = conclusion ?? item['status']?.toString() ?? 'unknown';
    final icon = switch (status) {
      'success' => Icons.check_circle_outline,
      'failure' => Icons.cancel_outlined,
      'in_progress' => Icons.pending_outlined,
      _ => Icons.help_outline,
    };
    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text('${item['name'] ?? 'Workflow'}'),
        subtitle: Text('${item['branch'] ?? '-'} • ${item['event'] ?? '-'}'),
        trailing: Chip(label: Text(status)),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Center(child: Text(label)),
      ),
    );
  }
}
