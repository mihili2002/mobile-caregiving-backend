import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class EmotionsScreen extends StatefulWidget {
  final String baseUrl;
  final String sessionId;

  const EmotionsScreen({
    super.key,
    required this.baseUrl,
    required this.sessionId,
  });

  @override
  State<EmotionsScreen> createState() => _EmotionsScreenState();
}

class _EmotionsScreenState extends State<EmotionsScreen> {
  bool _loading = true;
  String _error = "";
  List<Map<String, dynamic>> _emotionRows = [];

  // ---------- Brown theme colors ----------
  static const _brown900 = Color(0xFF3E2723);
  static const _brown800 = Color(0xFF4E342E);
  static const _brown200 = Color(0xFFD7CCC8);
  static const _cream = Color(0xFFF7F3EF);

  @override
  void initState() {
    super.initState();
    _loadEmotions();
  }

  Color _emotionColor(String emotion) {
    switch (emotion.toLowerCase()) {
      case 'happy':
      case 'joy':
        return Colors.green;
      case 'sad':
      case 'sadness':
        return Colors.blue;
      case 'angry':
      case 'anger':
        return Colors.red;
      case 'fear':
      case 'anxious':
        return Colors.orange;
      case 'lonely':
        return Colors.purple;
      default:
        return Colors.grey;
    }
  }

  DateTime? _parseCreatedAt(dynamic createdAt) {
    // backend returns createdAt like: "2025-12-22T15:06:35.601000+00:00"
    if (createdAt == null) return null;
    try {
      return DateTime.parse(createdAt.toString()).toLocal();
    } catch (_) {
      return null;
    }
  }

  String _fmtDate(DateTime dt) {
    final y = dt.year.toString().padLeft(4, '0');
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return "$y-$m-$d";
  }

  String _fmtTime(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return "$h:$m";
  }

  Future<void> _loadEmotions() async {
    setState(() {
      _loading = true;
      _error = "";
      _emotionRows = [];
    });

    try {
      // days=0 means "no filter" in your current API usage
      final uri = Uri.parse(
        "${widget.baseUrl}/chatbot/history/${widget.sessionId}?days=0",
      );

      final res = await http.get(uri);

      debugPrint("EMOTION HISTORY URL: $uri");
      debugPrint("STATUS: ${res.statusCode}");
      debugPrint("BODY: ${res.body}");

      if (res.statusCode != 200) {
        setState(() {
          _error = "Failed to load emotion history (${res.statusCode})";
          _loading = false;
        });
        return;
      }

      final data = jsonDecode(res.body);
      final msgs = (data["messages"] as List?) ?? [];

      // ✅ IMPORTANT: emotions are inside the "messages" list (usually bot messages)
      final rows = <Map<String, dynamic>>[];

      for (final m in msgs) {
        if (m is! Map) continue;

        final mm = m.map((k, v) => MapEntry(k.toString(), v));

        final emotion = mm["emotion"]?.toString();
        if (emotion == null || emotion.trim().isEmpty) continue; // keep only emotion rows

        final intent = mm["intent"]?.toString();
        final text = (mm["text"] ?? "").toString();
        final sender = (mm["sender"] ?? "").toString();

        final created = _parseCreatedAt(mm["createdAt"]);
        final displayTime = created != null
            ? "${_fmtDate(created)} ${_fmtTime(created)}"
            : (mm["displayTime"]?.toString() ?? "");

        rows.add({
          "emotion": emotion,
          "intent": intent ?? "none",
          "text": text,
          "sender": sender,
          "created": created,
          "displayTime": displayTime,
        });
      }

      // sort oldest -> newest (or flip if you want newest first)
      rows.sort((a, b) {
        final da = a["created"] as DateTime?;
        final db = b["created"] as DateTime?;
        if (da == null && db == null) return 0;
        if (da == null) return -1;
        if (db == null) return 1;
        return da.compareTo(db);
      });

      setState(() {
        _emotionRows = rows;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = "Error: $e";
        _loading = false;
      });
    }
  }

  PreferredSizeWidget _buildAppBar() {
    return AppBar(
      elevation: 0,
      backgroundColor: _brown900,
      title: const Text(
        "Emotion History",
        style: TextStyle(fontWeight: FontWeight.w700),
      ),
      actions: [
        IconButton(
          tooltip: "Refresh",
          icon: const Icon(Icons.refresh),
          onPressed: _loadEmotions,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _cream,
      appBar: _buildAppBar(),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error.isNotEmpty
              ? Center(
                  child: Text(
                    _error,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                )
              : _emotionRows.isEmpty
                  ? const Center(child: Text("No emotions yet"))
                  : ListView.separated(
                      padding: const EdgeInsets.all(14),
                      itemCount: _emotionRows.length,
                      separatorBuilder: (_, __) =>
                          Divider(color: _brown200.withOpacity(0.7)),
                      itemBuilder: (_, i) {
                        final row = _emotionRows[i];
                        final emotion = (row["emotion"] ?? "unknown").toString();
                        final intent = (row["intent"] ?? "none").toString();
                        final text = (row["text"] ?? "").toString();
                        final displayTime =
                            (row["displayTime"] ?? "").toString();

                        final color = _emotionColor(emotion);

                        return Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.95),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: _brown200.withOpacity(0.8),
                            ),
                            boxShadow: [
                              BoxShadow(
                                blurRadius: 16,
                                offset: const Offset(0, 7),
                                color: Colors.black.withOpacity(0.05),
                              )
                            ],
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              CircleAvatar(
                                backgroundColor: color,
                                child: const Icon(Icons.mood, color: Colors.white),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          emotion.toUpperCase(),
                                          style: TextStyle(
                                            fontWeight: FontWeight.w800,
                                            color: color,
                                          ),
                                        ),
                                        const SizedBox(width: 10),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 10, vertical: 6),
                                          decoration: BoxDecoration(
                                            color: _brown200.withOpacity(0.35),
                                            borderRadius:
                                                BorderRadius.circular(999),
                                          ),
                                          child: Text(
                                            "Intent: $intent",
                                            style: TextStyle(
                                              color: _brown800.withOpacity(0.9),
                                              fontWeight: FontWeight.w700,
                                              fontSize: 12,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      displayTime,
                                      style: TextStyle(
                                        color: _brown800.withOpacity(0.6),
                                        fontWeight: FontWeight.w700,
                                        fontSize: 12,
                                      ),
                                    ),
                                    const SizedBox(height: 10),
                                    Text(
                                      text,
                                      style: TextStyle(
                                        color: _brown800.withOpacity(0.95),
                                        height: 1.35,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
    );
  }
}