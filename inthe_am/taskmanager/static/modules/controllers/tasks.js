var controller = Ember.ArrayController.extend({
  sortProperties: ['urgency'],
  sortAscending: false,
  refresh: function(){
    this.get('content').update();
  },
  pendingTasks: function() {
    var result = this.get('model').filterProperty('status', 'pending');

    var sortedResult = Em.ArrayProxy.createWithMixins(
      Ember.SortableMixin,
      {
        content:result,
        sortProperties: this.sortProperties,
        sortAscending: false
      }
    );
    return sortedResult;
  }.property('model.@each.status')
});

module.exports = controller;
